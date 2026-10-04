from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_workspace_member
from app.core.rbac import CAN_APPROVE_CONTENT, require_role
from app.jobs.queue import get_arq_pool
from app.models.distribution import DistributionBatch, Publication
from app.models.identity import WorkspaceMember
from app.services.publishing.publishing_service import PublishingService

router = APIRouter(prefix="/workspaces/{workspace_id}/distributions", tags=["distributions"])


class PublicationResponse(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    status: str
    attempt: int
    error_code: str | None
    error_message: str | None
    telegram_message_id: int | None


class BatchResponse(BaseModel):
    id: uuid.UUID
    content_item_id: uuid.UUID
    status: str
    publications: list[PublicationResponse]


def _to_response(batch: DistributionBatch, publications: list[Publication]) -> BatchResponse:
    return BatchResponse(
        id=batch.id, content_item_id=batch.content_item_id, status=batch.status.value,
        publications=[
            PublicationResponse(
                id=p.id, channel_id=p.channel_id, status=p.status.value, attempt=p.attempt,
                error_code=p.error_code, error_message=p.error_message,
                telegram_message_id=p.telegram_message_id,
            )
            for p in publications
        ],
    )


@router.get("", response_model=list[BatchResponse])
async def list_batches_for_content(
    workspace_id: uuid.UUID, content_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    batches_result = await db.execute(
        select(DistributionBatch)
        .where(DistributionBatch.workspace_id == workspace_id, DistributionBatch.content_item_id == content_id)
        .order_by(DistributionBatch.created_at.desc())
    )
    batches = list(batches_result.scalars().all())
    if not batches:
        return []
    pubs_result = await db.execute(
        select(Publication).where(Publication.batch_id.in_([b.id for b in batches]))
    )
    by_batch: dict[uuid.UUID, list[Publication]] = {}
    for p in pubs_result.scalars().all():
        by_batch.setdefault(p.batch_id, []).append(p)
    return [_to_response(b, by_batch.get(b.id, [])) for b in batches]


@router.get("/{batch_id}", response_model=BatchResponse)
async def get_batch(
    workspace_id: uuid.UUID, batch_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    batch = await db.get(DistributionBatch, batch_id)
    if not batch or batch.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Distribution batch not found")
    pubs_result = await db.execute(select(Publication).where(Publication.batch_id == batch_id))
    return _to_response(batch, list(pubs_result.scalars().all()))


@router.post("/{batch_id}/retry-failed", response_model=BatchResponse)
async def retry_failed(
    workspace_id: uuid.UUID, batch_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_APPROVE_CONTENT)
    batch = await db.get(DistributionBatch, batch_id)
    if not batch or batch.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Distribution batch not found")

    service = PublishingService(db)
    retried_ids = await service.retry_failed(batch_id)

    # Put the content back into PUBLISHING so the scheduler keeps driving the
    # re-queued publications (and so the UI stops showing a final outcome).
    from app.models.content import ContentItem
    from app.models.enums import CONTENT_TRANSITIONS, ContentStatus

    item = await db.get(ContentItem, batch.content_item_id)
    if retried_ids and item and ContentStatus.PUBLISHING in CONTENT_TRANSITIONS.get(item.status, set()):
        item.status = ContentStatus.PUBLISHING
    await db.commit()

    pool = await get_arq_pool()
    for pub_id in retried_ids:
        await pool.enqueue_job("telegram_publish", str(pub_id))

    pubs_result = await db.execute(select(Publication).where(Publication.batch_id == batch_id))
    return _to_response(batch, list(pubs_result.scalars().all()))
