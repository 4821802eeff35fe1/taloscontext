from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_workspace_member
from app.core.rbac import CAN_APPROVE_CONTENT, require_role
from app.models.content import ContentItem
from app.models.distribution import DistributionBatch, Publication
from app.models.enums import CONTENT_TRANSITIONS, ContentStatus, JobType, PublicationStatus
from app.models.identity import User, WorkspaceMember
from app.models.telegram import TelegramChannel
from app.services.audit.service import AuditService
from app.services.jobs.service import JobService, dispatch
from app.services.publishing.publishing_service import DELIVERY_UNKNOWN, PublishingService
from app.services.realtime.events import publish_event

router = APIRouter(prefix="/workspaces/{workspace_id}/distributions", tags=["distributions"])


class PublicationResponse(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    channel_title: str | None = None
    channel_username: str | None = None
    status: str
    attempt: int
    error_code: str | None
    error_message: str | None
    flood_wait_seconds: int | None
    telegram_message_id: int | None
    published_at: datetime | None
    delivery_unknown: bool


class BatchResponse(BaseModel):
    id: uuid.UUID
    content_item_id: uuid.UUID
    status: str
    created_at: datetime
    publications: list[PublicationResponse]


class ResolveRequest(BaseModel):
    outcome: str  # "published" | "failed"


async def _channels(db: AsyncSession, publications: list[Publication]) -> dict[uuid.UUID, TelegramChannel]:
    ids = {p.channel_id for p in publications}
    if not ids:
        return {}
    rows = await db.execute(select(TelegramChannel).where(TelegramChannel.id.in_(ids)))
    return {c.id: c for c in rows.scalars().all()}


def _pub(p: Publication, channels: dict[uuid.UUID, TelegramChannel]) -> PublicationResponse:
    ch = channels.get(p.channel_id)
    return PublicationResponse(
        id=p.id, channel_id=p.channel_id, channel_title=ch.title if ch else None,
        channel_username=ch.username if ch else None, status=p.status.value, attempt=p.attempt,
        error_code=p.error_code, error_message=p.error_message, flood_wait_seconds=p.flood_wait_seconds,
        telegram_message_id=p.telegram_message_id, published_at=p.published_at,
        delivery_unknown=p.status in (PublicationStatus.SENDING, PublicationStatus.CLAIMED)
        and p.error_code == DELIVERY_UNKNOWN,
    )


async def _batch_response(db: AsyncSession, batch: DistributionBatch) -> BatchResponse:
    pubs = list((await db.execute(select(Publication).where(Publication.batch_id == batch.id))).scalars().all())
    channels = await _channels(db, pubs)
    pubs.sort(key=lambda p: (channels[p.channel_id].title if p.channel_id in channels else ""))
    return BatchResponse(
        id=batch.id, content_item_id=batch.content_item_id, status=batch.status.value,
        created_at=batch.created_at, publications=[_pub(p, channels) for p in pubs],
    )


async def _batch_or_404(db: AsyncSession, workspace_id: uuid.UUID, batch_id: uuid.UUID) -> DistributionBatch:
    batch = await db.get(DistributionBatch, batch_id)
    if not batch or batch.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Distribution batch not found")
    return batch


@router.get("", response_model=list[BatchResponse])
async def list_batches_for_content(
    workspace_id: uuid.UUID, content_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    batches = (
        await db.execute(
            select(DistributionBatch)
            .where(DistributionBatch.workspace_id == workspace_id, DistributionBatch.content_item_id == content_id)
            .order_by(DistributionBatch.created_at.desc())
        )
    ).scalars().all()
    return [await _batch_response(db, b) for b in batches]


@router.get("/{batch_id}", response_model=BatchResponse)
async def get_batch(
    workspace_id: uuid.UUID, batch_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    return await _batch_response(db, await _batch_or_404(db, workspace_id, batch_id))


@router.post("/{batch_id}/retry-failed", response_model=BatchResponse)
async def retry_failed(
    workspace_id: uuid.UUID, batch_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-queues only FAILED publications. Succeeded ones — and ones whose
    delivery is unknown — are never touched."""
    require_role(member.role, CAN_APPROVE_CONTENT)
    batch = await _batch_or_404(db, workspace_id, batch_id)
    retried_ids = await PublishingService(db).retry_failed(batch_id)
    if not retried_ids:
        raise HTTPException(status.HTTP_409_CONFLICT, "There are no failed publications to retry.")

    item = await db.get(ContentItem, batch.content_item_id)
    if item and ContentStatus.PUBLISHING in CONTENT_TRANSITIONS.get(item.status, set()):
        item.status = ContentStatus.PUBLISHING
    jobs_service = JobService(db)
    jobs = []
    channels = await _channels(db, [await db.get(Publication, pid) for pid in retried_ids])
    for pub_id in retried_ids:
        pub = await db.get(Publication, pub_id)
        ch = channels.get(pub.channel_id)
        jobs.append(await jobs_service.create(
            workspace_id=workspace_id, job_type=JobType.TELEGRAM_RETRY, payload={"publication_id": str(pub_id)},
            entity_type="publication", entity_id=pub_id, summary=f"Retry publish to {ch.title if ch else pub_id}",
            created_by_user_id=user.id, max_attempts=5,
        ))
    await AuditService(db).record(
        workspace_id=workspace_id, actor_user_id=user.id, action="publication.retry_requested",
        entity_type="distribution_batch", entity_id=batch.id, metadata={"publications": len(retried_ids)},
    )
    await db.commit()
    for job in jobs:
        await dispatch(job)
    await db.refresh(batch)
    return await _batch_response(db, batch)


@router.post("/publications/{publication_id}/resolve", response_model=BatchResponse)
async def resolve_publication(
    workspace_id: uuid.UUID, publication_id: uuid.UUID, payload: ResolveRequest,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Human decision for a publication whose delivery state is unknown."""
    require_role(member.role, CAN_APPROVE_CONTENT)
    pub = await db.get(Publication, publication_id)
    batch = await db.get(DistributionBatch, pub.batch_id) if pub else None
    if pub is None or batch is None or batch.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Publication not found")
    try:
        await PublishingService(db).resolve_unknown(pub, outcome=payload.outcome)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await AuditService(db).record(
        workspace_id=workspace_id, actor_user_id=user.id, action=f"publication.marked_{payload.outcome}",
        entity_type="publication", entity_id=pub.id,
    )
    await db.commit()
    await publish_event(workspace_id, "publication.published" if payload.outcome == "published" else "publication.failed",
                        {"publication_id": str(pub.id), "batch_id": str(batch.id)})
    return await _batch_response(db, batch)
