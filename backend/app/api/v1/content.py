from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_workspace_member
from app.core.rbac import CAN_APPROVE_CONTENT, CAN_EDIT_CONTENT, require_role
from app.models.content import ContentItem
from app.models.identity import User, WorkspaceMember
from app.services.ai.factory import get_image_provider, get_text_provider
from app.services.ai.service import AIService
from app.services.content.service import ContentService, InvalidTransitionError
from app.services.knowledge.service import KnowledgeService
from app.services.publishing.distribution_service import DistributionService

router = APIRouter(prefix="/workspaces/{workspace_id}/content", tags=["content"])


def _content_service(db: AsyncSession) -> ContentService:
    ai_service = AIService(db, get_text_provider(), get_image_provider())
    return ContentService(db, ai_service)


class ContentResponse(BaseModel):
    id: uuid.UUID
    status: str
    topic: str
    category: str
    title: str
    plain_text: str
    telegram_html: str
    cta_key: str | None
    tags: list[str]
    duplicate_score: float | None
    requires_review: bool
    scheduled_at: datetime | None
    published_at: datetime | None

    @classmethod
    def from_model(cls, item: ContentItem) -> ContentResponse:
        return cls(
            id=item.id, status=item.status.value, topic=item.topic, category=item.category,
            title=item.title, plain_text=item.plain_text, telegram_html=item.telegram_html,
            cta_key=item.cta_key, tags=json.loads(item.tags_json or "[]"),
            duplicate_score=item.duplicate_score, requires_review=item.requires_review,
            scheduled_at=item.scheduled_at, published_at=item.published_at,
        )


class GenerateRequest(BaseModel):
    instruction: str
    channel_set_id: uuid.UUID | None = None
    tone_profile_id: uuid.UUID | None = None


class EditRequest(BaseModel):
    title: str
    telegram_html: str
    plain_text: str


class ScheduleRequest(BaseModel):
    scheduled_at: datetime


@router.get("", response_model=list[ContentResponse])
async def list_content(
    workspace_id: uuid.UUID,
    status_filter: str | None = None,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: AsyncSession = Depends(get_db),
):
    query = select(ContentItem).where(ContentItem.workspace_id == workspace_id)
    if status_filter:
        query = query.where(ContentItem.status == status_filter)
    result = await db.execute(query.order_by(ContentItem.created_at.desc()).limit(200))
    return [ContentResponse.from_model(i) for i in result.scalars().all()]


@router.get("/{content_id}", response_model=ContentResponse)
async def get_content(
    workspace_id: uuid.UUID,
    content_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: AsyncSession = Depends(get_db),
):
    item = await _get_or_404(db, workspace_id, content_id)
    return ContentResponse.from_model(item)


@router.post("/generate", response_model=ContentResponse, status_code=status.HTTP_201_CREATED)
async def generate(
    workspace_id: uuid.UUID,
    payload: GenerateRequest,
    member: WorkspaceMember = Depends(get_workspace_member),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    knowledge_service = KnowledgeService(db)
    knowledge_context = await knowledge_service.build_context(workspace_id=workspace_id)

    service = _content_service(db)
    try:
        item = await service.generate(
            workspace_id=workspace_id,
            user_id=user.id,
            user_instruction=payload.instruction,
            knowledge_context=knowledge_context,
            channel_set_id=payload.channel_set_id,
            tone_profile_id=payload.tone_profile_id,
        )
    except Exception as exc:
        await db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI generation failed: {exc}") from exc
    await db.commit()
    return ContentResponse.from_model(item)


@router.patch("/{content_id}", response_model=ContentResponse)
async def edit_content(
    workspace_id: uuid.UUID,
    content_id: uuid.UUID,
    payload: EditRequest,
    member: WorkspaceMember = Depends(get_workspace_member),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    item = await _get_or_404(db, workspace_id, content_id)
    service = _content_service(db)
    item = await service.manual_edit(
        item=item, user_id=user.id, title=payload.title,
        telegram_html=payload.telegram_html, plain_text=payload.plain_text,
    )
    await db.commit()
    return ContentResponse.from_model(item)


@router.post("/{content_id}/submit", response_model=ContentResponse)
async def submit_for_approval(
    workspace_id: uuid.UUID, content_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    item = await _get_or_404(db, workspace_id, content_id)
    service = _content_service(db)
    item = await _run_transition(service.submit_for_approval, item)
    await db.commit()
    return ContentResponse.from_model(item)


@router.post("/{content_id}/approve", response_model=ContentResponse)
async def approve(
    workspace_id: uuid.UUID, content_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_APPROVE_CONTENT)
    item = await _get_or_404(db, workspace_id, content_id)
    service = _content_service(db)
    item = await _run_transition(service.approve, item)
    await db.commit()
    return ContentResponse.from_model(item)


@router.post("/{content_id}/reject", response_model=ContentResponse)
async def reject(
    workspace_id: uuid.UUID, content_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_APPROVE_CONTENT)
    item = await _get_or_404(db, workspace_id, content_id)
    service = _content_service(db)
    item = await _run_transition(service.reject, item)
    await db.commit()
    return ContentResponse.from_model(item)


@router.post("/{content_id}/schedule", response_model=ContentResponse)
async def schedule_content(
    workspace_id: uuid.UUID, content_id: uuid.UUID, payload: ScheduleRequest,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_APPROVE_CONTENT)
    item = await _get_or_404(db, workspace_id, content_id)
    service = _content_service(db)
    try:
        item = await service.schedule(item, scheduled_at=payload.scheduled_at)
    except InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    if item.channel_set_id:
        distribution_service = DistributionService(db)
        from app.models.enums import ChannelSetMode
        from app.models.telegram import ChannelSet

        channel_set = await db.get(ChannelSet, item.channel_set_id)
        await distribution_service.create_batch(
            content_item=item,
            channel_set_id=item.channel_set_id,
            mode=channel_set.mode if channel_set else ChannelSetMode.EXACT,
            workspace_cta_defaults={},
        )

    await db.commit()
    return ContentResponse.from_model(item)


async def _run_transition(fn, item: ContentItem) -> ContentItem:
    try:
        return await fn(item)
    except InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


async def _get_or_404(db: AsyncSession, workspace_id: uuid.UUID, content_id: uuid.UUID) -> ContentItem:
    item = await db.get(ContentItem, content_id)
    if not item or item.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content item not found")
    return item
