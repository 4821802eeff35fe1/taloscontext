from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_workspace_member
from app.core.errors import ApiError
from app.core.rbac import CAN_EDIT_CONTENT, require_role
from app.models.content import ContentSeries
from app.models.identity import User, WorkspaceMember
from app.models.knowledge import ToneOfVoiceProfile
from app.models.scheduling import Schedule
from app.models.telegram import ChannelSet
from app.services.audit.service import AuditService
from app.services.content.series_service import SERIES_STATUSES, SeriesService

router = APIRouter(prefix="/workspaces/{workspace_id}/series", tags=["series"])


class SeriesIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=4000)
    channel_set_id: uuid.UUID | None = None
    tone_profile_id: uuid.UUID | None = None
    schedule_id: uuid.UUID | None = None
    category: str = Field(default="", max_length=100)
    status: str = "DRAFT"
    numbering_format: str = Field(default="#{n:03d}", max_length=40)
    planned_topics: list[str] = Field(default_factory=list, max_length=500)

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in SERIES_STATUSES:
            raise ValueError(f"status must be one of {', '.join(SERIES_STATUSES)}")
        return v

    @field_validator("numbering_format")
    @classmethod
    def _fmt(cls, v: str) -> str:
        try:
            v.format(n=1)
        except (KeyError, ValueError, IndexError) as exc:
            raise ValueError('numbering_format must use {n}, e.g. "#{n:03d}" or "Part {n}"') from exc
        return v


class SeriesItemOut(BaseModel):
    label: str
    number: int
    title: str
    status: str
    content_id: str


class SeriesOut(SeriesIn):
    id: uuid.UUID
    channel_set_name: str | None
    tone_profile_name: str | None
    published_count: int
    planned_count: int
    next_topic: str | None
    next_label: str
    remaining_topics: list[str]
    items: list[SeriesItemOut]
    in_progress: list[SeriesItemOut]
    updated_at: datetime


async def _out(db: AsyncSession, s: ContentSeries) -> SeriesOut:
    progress = await SeriesService(db).progress(s)
    cs = await db.get(ChannelSet, s.channel_set_id) if s.channel_set_id else None
    tone = await db.get(ToneOfVoiceProfile, s.tone_profile_id) if s.tone_profile_id else None
    return SeriesOut(
        id=s.id, title=s.title, description=s.description, channel_set_id=s.channel_set_id,
        tone_profile_id=s.tone_profile_id, schedule_id=s.schedule_id, category=s.category, status=s.status,
        numbering_format=s.numbering_format, planned_topics=json.loads(s.planned_topics_json or "[]"),
        channel_set_name=cs.name if cs else None, tone_profile_name=tone.name if tone else None,
        published_count=progress["published_count"], planned_count=progress["planned_count"],
        next_topic=progress["next_topic"], next_label=progress["next_label"],
        remaining_topics=progress["remaining_topics"], items=progress["items"], in_progress=progress["in_progress"],
        updated_at=s.updated_at,
    )


async def _check_refs(db, workspace_id, payload: SeriesIn) -> None:
    for model, value, label in ((ChannelSet, payload.channel_set_id, "Channel set"),
                                (ToneOfVoiceProfile, payload.tone_profile_id, "Tone profile"),
                                (Schedule, payload.schedule_id, "Schedule")):
        if value is not None:
            obj = await db.get(model, value)
            if obj is None or obj.workspace_id != workspace_id:
                raise ApiError(404, "REFERENCE_NOT_FOUND", f"{label} not found", entity=label)


def _apply(s: ContentSeries, p: SeriesIn) -> None:
    s.title, s.description, s.category, s.status = p.title, p.description, p.category, p.status
    s.channel_set_id, s.tone_profile_id, s.schedule_id = p.channel_set_id, p.tone_profile_id, p.schedule_id
    s.numbering_format = p.numbering_format
    s.planned_topics_json = json.dumps([t.strip() for t in p.planned_topics if t.strip()], ensure_ascii=False)


async def _get(db, workspace_id, series_id) -> ContentSeries:
    s = await SeriesService(db).get_for_workspace(workspace_id, series_id)
    if s is None:
        raise ApiError(404, "SERIES_NOT_FOUND", "Series not found")
    return s


@router.get("", response_model=list[SeriesOut])
async def list_series(workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member),
                      db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ContentSeries).where(ContentSeries.workspace_id == workspace_id)
                             .order_by(ContentSeries.created_at.desc()))).scalars().all()
    return [await _out(db, s) for s in rows]


@router.post("", response_model=SeriesOut, status_code=status.HTTP_201_CREATED)
async def create_series(workspace_id: uuid.UUID, payload: SeriesIn, member: WorkspaceMember = Depends(get_workspace_member),
                        user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_role(member.role, CAN_EDIT_CONTENT)
    await _check_refs(db, workspace_id, payload)
    s = ContentSeries(workspace_id=workspace_id, title=payload.title)
    _apply(s, payload)
    db.add(s)
    await db.flush()
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="series.created",
                                  entity_type="series", entity_id=s.id, metadata={"title": s.title})
    await db.commit()
    return await _out(db, s)


@router.get("/{series_id}", response_model=SeriesOut)
async def get_series(workspace_id: uuid.UUID, series_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member),
                     db: AsyncSession = Depends(get_db)):
    return await _out(db, await _get(db, workspace_id, series_id))


@router.put("/{series_id}", response_model=SeriesOut)
async def update_series(workspace_id: uuid.UUID, series_id: uuid.UUID, payload: SeriesIn,
                        member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    require_role(member.role, CAN_EDIT_CONTENT)
    s = await _get(db, workspace_id, series_id)
    await _check_refs(db, workspace_id, payload)
    _apply(s, payload)
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="series.updated",
                                  entity_type="series", entity_id=s.id, metadata={"status": s.status})
    await db.commit()
    return await _out(db, s)


@router.delete("/{series_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_series(workspace_id: uuid.UUID, series_id: uuid.UUID,
                        member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """Posts stay; they just stop being part of the series."""
    require_role(member.role, CAN_EDIT_CONTENT)
    s = await _get(db, workspace_id, series_id)
    await db.delete(s)
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="series.deleted",
                                  entity_type="series", entity_id=series_id, metadata={"title": s.title})
    await db.commit()

