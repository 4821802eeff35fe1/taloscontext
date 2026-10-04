from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_workspace_member
from app.core.rbac import CAN_APPROVE_CONTENT, require_role
from app.jobs.scheduler import MISFIRE_POLICIES
from app.models.content import ContentItem
from app.models.enums import ContentStatus
from app.models.identity import User, WorkspaceMember
from app.models.scheduling import Schedule, ScheduleRule
from app.models.telegram import ChannelSet
from app.services.audit.service import AuditService
from app.services.scheduling.service import (
    ScheduleService,
    ScheduleValidationError,
    validate_timezone,
    validate_windows,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/schedules", tags=["schedules"])


class WindowIn(BaseModel):
    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")


class ScheduleIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    channel_set_id: uuid.UUID | None = None
    timezone: str = "UTC"
    days_of_week: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    posts_per_day: int = Field(default=1, ge=1, le=48)
    windows: list[WindowIn] = Field(min_length=1, max_length=24)
    randomize: bool = True
    min_interval_minutes: int = Field(default=60, ge=0, le=24 * 60)
    max_posts_per_day: int = Field(default=10, ge=1, le=96)
    categories: list[str] = Field(default_factory=list, max_length=20)
    exclude_dates: list[date] = Field(default_factory=list, max_length=366)
    enabled: bool = True
    misfire_policy: str | None = None

    @field_validator("days_of_week")
    @classmethod
    def _days(cls, v: list[int]) -> list[int]:
        if not v or any(d < 0 or d > 6 for d in v):
            raise ValueError("days_of_week must contain values 0 (Mon) .. 6 (Sun)")
        return sorted(set(v))

    @field_validator("misfire_policy")
    @classmethod
    def _misfire(cls, v: str | None) -> str | None:
        if v is not None and v not in MISFIRE_POLICIES:
            raise ValueError(f"misfire_policy must be one of {', '.join(MISFIRE_POLICIES)}")
        return v


class ScheduleOut(BaseModel):
    id: uuid.UUID
    name: str
    channel_set_id: uuid.UUID | None
    channel_set_name: str | None
    timezone: str
    days_of_week: list[int]
    posts_per_day: int
    windows: list[WindowIn]
    randomize: bool
    min_interval_minutes: int
    max_posts_per_day: int
    categories: list[str]
    exclude_dates: list[str]
    enabled: bool
    misfire_policy: str | None
    scheduled_count: int
    next_slots: list[datetime]


async def _out(db: AsyncSession, s: Schedule) -> ScheduleOut:
    rules = (await db.execute(select(ScheduleRule).where(ScheduleRule.schedule_id == s.id)
                              .order_by(ScheduleRule.window_start))).scalars().all()
    cs = await db.get(ChannelSet, s.channel_set_id) if s.channel_set_id else None
    scheduled = await db.scalar(select(func.count()).select_from(ContentItem).where(
        ContentItem.schedule_id == s.id, ContentItem.status == ContentStatus.SCHEDULED))
    return ScheduleOut(
        id=s.id, name=s.name, channel_set_id=s.channel_set_id, channel_set_name=cs.name if cs else None,
        timezone=s.timezone, days_of_week=json.loads(s.days_of_week_json or "[]"), posts_per_day=s.posts_per_day,
        windows=[WindowIn(start=r.window_start, end=r.window_end) for r in rules],
        randomize=s.randomize_within_window, min_interval_minutes=s.min_interval_minutes,
        max_posts_per_day=s.max_posts_per_day, categories=json.loads(s.categories_json or "[]"),
        exclude_dates=json.loads(s.exclude_dates_json or "[]"), enabled=not s.is_paused,
        misfire_policy=s.misfire_policy, scheduled_count=scheduled or 0,
        next_slots=ScheduleService().upcoming(s, list(rules), after=datetime.now(UTC), limit=5),
    )


async def _apply(db: AsyncSession, workspace_id: uuid.UUID, s: Schedule, payload: ScheduleIn) -> None:
    try:
        validate_timezone(payload.timezone)
        windows = validate_windows([(w.start, w.end) for w in payload.windows])
    except ScheduleValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    if payload.channel_set_id:
        cs = await db.get(ChannelSet, payload.channel_set_id)
        if cs is None or cs.workspace_id != workspace_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel set not found")
    s.name = payload.name
    s.channel_set_id = payload.channel_set_id
    s.timezone = payload.timezone
    s.days_of_week_json = json.dumps(payload.days_of_week)
    s.posts_per_day = payload.posts_per_day
    s.randomize_within_window = payload.randomize
    s.min_interval_minutes = payload.min_interval_minutes
    s.max_posts_per_day = payload.max_posts_per_day
    s.categories_json = json.dumps(payload.categories, ensure_ascii=False)
    s.exclude_dates_json = json.dumps(sorted(d.isoformat() for d in payload.exclude_dates))
    s.is_paused = not payload.enabled
    s.misfire_policy = payload.misfire_policy
    await db.flush()
    for old in (await db.execute(select(ScheduleRule).where(ScheduleRule.schedule_id == s.id))).scalars().all():
        await db.delete(old)
    await db.flush()
    for w in windows:
        db.add(ScheduleRule(schedule_id=s.id, window_start=w.start.strftime("%H:%M"), window_end=w.end.strftime("%H:%M")))
    await db.flush()


async def _get(db: AsyncSession, workspace_id: uuid.UUID, schedule_id: uuid.UUID) -> Schedule:
    s = await db.get(Schedule, schedule_id)
    if s is None or s.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")
    return s


@router.get("", response_model=list[ScheduleOut])
async def list_schedules(
    workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db)
):
    rows = (await db.execute(select(Schedule).where(Schedule.workspace_id == workspace_id).order_by(Schedule.created_at))).scalars().all()
    return [await _out(db, s) for s in rows]


@router.post("", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    workspace_id: uuid.UUID, payload: ScheduleIn,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_APPROVE_CONTENT)
    s = Schedule(workspace_id=workspace_id, name=payload.name)
    db.add(s)
    await db.flush()
    await _apply(db, workspace_id, s, payload)
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="schedule.created",
                                  entity_type="schedule", entity_id=s.id, metadata={"name": s.name})
    await db.commit()
    return await _out(db, s)


@router.put("/{schedule_id}", response_model=ScheduleOut)
async def update_schedule(
    workspace_id: uuid.UUID, schedule_id: uuid.UUID, payload: ScheduleIn,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_APPROVE_CONTENT)
    s = await _get(db, workspace_id, schedule_id)
    await _apply(db, workspace_id, s, payload)
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="schedule.updated",
                                  entity_type="schedule", entity_id=s.id, metadata={"enabled": payload.enabled})
    await db.commit()
    return await _out(db, s)


@router.post("/{schedule_id}/pause", response_model=ScheduleOut)
async def pause_schedule(
    workspace_id: uuid.UUID, schedule_id: uuid.UUID, paused: bool = True,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_APPROVE_CONTENT)
    s = await _get(db, workspace_id, schedule_id)
    s.is_paused = paused
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id,
                                  action="schedule.paused" if paused else "schedule.resumed",
                                  entity_type="schedule", entity_id=s.id)
    await db.commit()
    return await _out(db, s)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    workspace_id: uuid.UUID, schedule_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Already scheduled posts keep their time; they just lose the link to the rule."""
    require_role(member.role, CAN_APPROVE_CONTENT)
    s = await _get(db, workspace_id, schedule_id)
    await db.delete(s)
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="schedule.deleted",
                                  entity_type="schedule", entity_id=schedule_id, metadata={"name": s.name})
    await db.commit()


@router.post("/preview", response_model=list[datetime])
async def preview_schedule(
    workspace_id: uuid.UUID, payload: ScheduleIn, member: WorkspaceMember = Depends(get_workspace_member),
):
    """Upcoming slots for an unsaved schedule — live preview in the editor."""
    try:
        validate_timezone(payload.timezone)
        windows = validate_windows([(w.start, w.end) for w in payload.windows])
    except ScheduleValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    s = Schedule(
        id=uuid.uuid4(), workspace_id=workspace_id, name=payload.name, timezone=payload.timezone,
        days_of_week_json=json.dumps(payload.days_of_week), posts_per_day=payload.posts_per_day,
        randomize_within_window=payload.randomize, min_interval_minutes=payload.min_interval_minutes,
        max_posts_per_day=payload.max_posts_per_day, is_paused=False,
        exclude_dates_json=json.dumps([d.isoformat() for d in payload.exclude_dates]),
    )
    rules = [ScheduleRule(window_start=w.start.strftime("%H:%M"), window_end=w.end.strftime("%H:%M")) for w in windows]
    return ScheduleService().upcoming(s, rules, after=datetime.now(UTC), limit=14)
