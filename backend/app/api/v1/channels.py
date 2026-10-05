from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_workspace_member
from app.core.errors import ApiError
from app.core.rbac import CAN_MANAGE_TELEGRAM, require_role
from app.models.analytics import PostMetricSnapshot
from app.models.content import ContentItem
from app.models.distribution import DistributionBatch, Publication
from app.models.enums import ChannelSetMode, ContentStatus, PublicationStatus
from app.models.identity import User, WorkspaceMember
from app.models.knowledge import ToneOfVoiceProfile
from app.models.scheduling import Schedule
from app.models.telegram import ChannelSet, ChannelSetMember, TelegramAccount, TelegramChannel
from app.services.audit.service import AuditService
from app.services.content.cta_resolver import KNOWN_CTA_KEYS
from app.services.scheduling.service import ScheduleValidationError, validate_timezone

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["channels"])


class ChannelResponse(BaseModel):
    id: uuid.UUID
    title: str
    username: str | None
    can_post: bool
    health: str
    subscriber_count: int | None
    autopilot_enabled: bool
    default_cta_key: str | None
    timezone: str
    tone_profile_id: uuid.UUID | None
    cta_overrides: dict[str, str]
    account_id: uuid.UUID
    account_label: str
    account_status: str
    last_published_at: datetime | None
    next_scheduled_at: datetime | None
    posts_30d: int


class ChannelUpdateRequest(BaseModel):
    autopilot_enabled: bool | None = None
    default_cta_key: str | None = None
    timezone: str | None = None
    tone_profile_id: uuid.UUID | None = None
    clear_tone_profile: bool = False
    cta_overrides: dict[str, str] | None = None

    @field_validator("cta_overrides")
    @classmethod
    def _cta(cls, v):
        if v is None:
            return v
        unknown = set(v) - KNOWN_CTA_KEYS
        if unknown:
            raise ValueError(f"Unknown CTA keys: {', '.join(sorted(unknown))}")
        return {k: s.strip()[:300] for k, s in v.items() if s and s.strip()}


class ChannelSetIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    mode: ChannelSetMode = ChannelSetMode.EXACT
    channel_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)


class ChannelSetResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    mode: str
    autopilot_enabled: bool
    member_count: int
    healthy_count: int
    subscribers: int


class SetPost(BaseModel):
    content_id: uuid.UUID
    title: str
    status: str
    published_at: datetime | None
    scheduled_at: datetime | None
    targets: int
    published: int
    failed: int
    views: int


class ChannelSetDetail(ChannelSetResponse):
    channels: list[ChannelResponse]
    recent_posts: list[SetPost]
    totals: dict
    schedules: list[dict]


async def _channel_responses(db: AsyncSession, channels: list[TelegramChannel]) -> list[ChannelResponse]:
    if not channels:
        return []
    ids = [c.id for c in channels]
    accounts = {a.id: a for a in (await db.execute(select(TelegramAccount).where(
        TelegramAccount.id.in_({c.account_id for c in channels})))).scalars().all()}
    last_pub = dict((await db.execute(
        select(Publication.channel_id, func.max(Publication.published_at))
        .where(Publication.channel_id.in_(ids), Publication.status == PublicationStatus.SUCCESS)
        .group_by(Publication.channel_id))).all())
    since = datetime.now(UTC) - timedelta(days=30)
    posts = dict((await db.execute(
        select(Publication.channel_id, func.count())
        .where(Publication.channel_id.in_(ids), Publication.status == PublicationStatus.SUCCESS,
               Publication.published_at >= since)
        .group_by(Publication.channel_id))).all())
    next_rows = (await db.execute(
        select(ChannelSetMember.channel_id, func.min(ContentItem.scheduled_at))
        .join(ContentItem, ContentItem.channel_set_id == ChannelSetMember.channel_set_id)
        .where(ChannelSetMember.channel_id.in_(ids), ContentItem.status == ContentStatus.SCHEDULED,
               ContentItem.deleted_at.is_(None))
        .group_by(ChannelSetMember.channel_id))).all()
    next_at = dict(next_rows)
    out = []
    for c in channels:
        a = accounts.get(c.account_id)
        out.append(ChannelResponse(
            id=c.id, title=c.title, username=c.username, can_post=c.can_post, health=c.health.value,
            subscriber_count=c.subscriber_count, autopilot_enabled=c.autopilot_enabled,
            default_cta_key=c.default_cta_key, timezone=c.timezone, tone_profile_id=c.tone_profile_id,
            cta_overrides=json.loads(c.cta_overrides_json or "{}"), account_id=c.account_id,
            account_label=(f"{a.first_name} {a.last_name}".strip() or a.phone_masked) if a else "",
            account_status=a.status.value if a else "UNKNOWN", last_published_at=last_pub.get(c.id),
            next_scheduled_at=next_at.get(c.id), posts_30d=posts.get(c.id, 0),
        ))
    return out


async def _set_responses(db: AsyncSession, sets: list[ChannelSet]) -> list[ChannelSetResponse]:
    if not sets:
        return []
    rows = (await db.execute(
        select(ChannelSetMember.channel_set_id, func.count(), func.sum(case((TelegramChannel.can_post.is_(True), 1), else_=0)),
               func.coalesce(func.sum(TelegramChannel.subscriber_count), 0))
        .join(TelegramChannel, TelegramChannel.id == ChannelSetMember.channel_id)
        .where(ChannelSetMember.channel_set_id.in_([s.id for s in sets]))
        .group_by(ChannelSetMember.channel_set_id))).all()
    stats = {sid: (n, int(h or 0), int(subs or 0)) for sid, n, h, subs in rows}
    return [ChannelSetResponse(id=s.id, name=s.name, description=s.description, mode=s.mode.value,
                               autopilot_enabled=s.autopilot_enabled, member_count=stats.get(s.id, (0, 0, 0))[0],
                               healthy_count=stats.get(s.id, (0, 0, 0))[1], subscribers=stats.get(s.id, (0, 0, 0))[2])
            for s in sets]


@router.get("/channels", response_model=list[ChannelResponse])
async def list_channels(
    workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db)
):
    channels = (await db.execute(select(TelegramChannel).where(TelegramChannel.workspace_id == workspace_id)
                                 .order_by(TelegramChannel.title))).scalars().all()
    return await _channel_responses(db, list(channels))


@router.patch("/channels/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    workspace_id: uuid.UUID, channel_id: uuid.UUID, payload: ChannelUpdateRequest,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_MANAGE_TELEGRAM)
    channel = await db.get(TelegramChannel, channel_id)
    if not channel or channel.workspace_id != workspace_id:
        raise ApiError(404, "CHANNEL_NOT_FOUND", "Channel not found")
    if payload.tone_profile_id:
        tone = await db.get(ToneOfVoiceProfile, payload.tone_profile_id)
        if tone is None or tone.workspace_id != workspace_id:
            raise ApiError(404, "TONE_PROFILE_NOT_FOUND", "Tone profile not found")
        channel.tone_profile_id = tone.id
    if payload.clear_tone_profile:
        channel.tone_profile_id = None
    if payload.timezone is not None:
        try:
            channel.timezone = validate_timezone(payload.timezone)
        except ScheduleValidationError as exc:
            raise ApiError(422, "TIMEZONE_INVALID", str(exc)) from exc
    if payload.autopilot_enabled is not None:
        channel.autopilot_enabled = payload.autopilot_enabled
    if payload.default_cta_key is not None:
        if payload.default_cta_key and payload.default_cta_key not in KNOWN_CTA_KEYS:
            raise ApiError(422, "CTA_KEY_UNKNOWN", "Unknown CTA key")
        channel.default_cta_key = payload.default_cta_key or None
    if payload.cta_overrides is not None:
        channel.cta_overrides_json = json.dumps(payload.cta_overrides, ensure_ascii=False)
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="channel.updated",
                                  entity_type="channel", entity_id=channel.id,
                                  metadata=payload.model_dump(exclude_none=True, mode="json"))
    await db.commit()
    return (await _channel_responses(db, [channel]))[0]


async def _members_valid(db: AsyncSession, workspace_id: uuid.UUID, ids: list[uuid.UUID]) -> None:
    if not ids:
        return
    owned = await db.scalar(select(func.count()).select_from(TelegramChannel).where(
        TelegramChannel.id.in_(ids), TelegramChannel.workspace_id == workspace_id))
    if owned != len(set(ids)):
        raise ApiError(400, "CHANNELS_NOT_IN_WORKSPACE", "One or more channels do not belong to this workspace")


@router.get("/channel-sets", response_model=list[ChannelSetResponse])
async def list_channel_sets(
    workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db)
):
    sets = (await db.execute(select(ChannelSet).where(ChannelSet.workspace_id == workspace_id)
                             .order_by(ChannelSet.name))).scalars().all()
    return await _set_responses(db, list(sets))


@router.post("/channel-sets", response_model=ChannelSetResponse, status_code=status.HTTP_201_CREATED)
async def create_channel_set(
    workspace_id: uuid.UUID, payload: ChannelSetIn,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_MANAGE_TELEGRAM)
    await _members_valid(db, workspace_id, payload.channel_ids)
    channel_set = ChannelSet(workspace_id=workspace_id, name=payload.name, description=payload.description,
                             mode=payload.mode)
    db.add(channel_set)
    await db.flush()
    for channel_id in dict.fromkeys(payload.channel_ids):
        db.add(ChannelSetMember(channel_set_id=channel_set.id, channel_id=channel_id))
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="channel_set.created",
                                  entity_type="channel_set", entity_id=channel_set.id,
                                  metadata={"name": payload.name, "channels": len(payload.channel_ids)})
    await db.commit()
    return (await _set_responses(db, [channel_set]))[0]


async def _set_or_404(db, workspace_id, set_id) -> ChannelSet:
    cs = await db.get(ChannelSet, set_id)
    if cs is None or cs.workspace_id != workspace_id:
        raise ApiError(404, "CHANNEL_SET_NOT_FOUND", "Channel set not found")
    return cs


@router.get("/channel-sets/{set_id}", response_model=ChannelSetDetail)
async def get_channel_set(
    workspace_id: uuid.UUID, set_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    from app.api.v1.content import _delivery_stats

    cs = await _set_or_404(db, workspace_id, set_id)
    channels = (await db.execute(
        select(TelegramChannel).join(ChannelSetMember, ChannelSetMember.channel_id == TelegramChannel.id)
        .where(ChannelSetMember.channel_set_id == cs.id).order_by(TelegramChannel.title))).scalars().all()
    items = (await db.execute(select(ContentItem).where(
        ContentItem.channel_set_id == cs.id, ContentItem.deleted_at.is_(None),
        ContentItem.status.in_([ContentStatus.SCHEDULED, ContentStatus.PUBLISHING, ContentStatus.PUBLISHED,
                                ContentStatus.PARTIALLY_PUBLISHED, ContentStatus.FAILED]))
        .order_by(func.coalesce(ContentItem.published_at, ContentItem.scheduled_at).desc()).limit(15))).scalars().all()
    stats = await _delivery_stats(db, [i.id for i in items])

    latest = (select(PostMetricSnapshot.publication_id, func.max(PostMetricSnapshot.captured_at).label("at"))
              .group_by(PostMetricSnapshot.publication_id).subquery())
    totals_row = (await db.execute(
        select(func.count(Publication.id), func.coalesce(func.sum(PostMetricSnapshot.views), 0),
               func.coalesce(func.sum(PostMetricSnapshot.forwards), 0), func.coalesce(func.sum(PostMetricSnapshot.reactions), 0))
        .join(DistributionBatch, Publication.batch_id == DistributionBatch.id)
        .outerjoin(latest, latest.c.publication_id == Publication.id)
        .outerjoin(PostMetricSnapshot, and_(PostMetricSnapshot.publication_id == Publication.id,
                                            PostMetricSnapshot.captured_at == latest.c.at))
        .where(DistributionBatch.channel_set_id == cs.id, Publication.status == PublicationStatus.SUCCESS))).one()
    schedules = (await db.execute(select(Schedule).where(Schedule.channel_set_id == cs.id))).scalars().all()
    base = (await _set_responses(db, [cs]))[0]
    return ChannelSetDetail(
        **base.model_dump(),
        channels=await _channel_responses(db, list(channels)),
        recent_posts=[SetPost(content_id=i.id, title=i.title or i.topic or "", status=i.status.value,
                              published_at=i.published_at, scheduled_at=i.scheduled_at, targets=stats[i.id]["targets"],
                              published=stats[i.id]["published"], failed=stats[i.id]["failed"], views=stats[i.id]["views"])
                      for i in items],
        totals={"publications": totals_row[0], "views": int(totals_row[1]), "forwards": int(totals_row[2]),
                "reactions": int(totals_row[3])},
        schedules=[{"id": str(s.id), "name": s.name, "enabled": not s.is_paused, "posts_per_day": s.posts_per_day}
                   for s in schedules],
    )


@router.put("/channel-sets/{set_id}", response_model=ChannelSetResponse)
async def update_channel_set(
    workspace_id: uuid.UUID, set_id: uuid.UUID, payload: ChannelSetIn,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Membership changes apply to batches built from now on; already-scheduled
    posts pick them up because their untouched batches are rebuilt on edit/reschedule."""
    require_role(member.role, CAN_MANAGE_TELEGRAM)
    cs = await _set_or_404(db, workspace_id, set_id)
    await _members_valid(db, workspace_id, payload.channel_ids)
    current = {m.channel_id: m for m in (await db.execute(
        select(ChannelSetMember).where(ChannelSetMember.channel_set_id == cs.id))).scalars().all()}
    wanted = set(payload.channel_ids)
    for channel_id, m in current.items():
        if channel_id not in wanted:
            await db.delete(m)
    for channel_id in wanted - set(current):
        db.add(ChannelSetMember(channel_set_id=cs.id, channel_id=channel_id))
    cs.name, cs.description, cs.mode = payload.name, payload.description, payload.mode
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="channel_set.updated",
                                  entity_type="channel_set", entity_id=cs.id,
                                  metadata={"name": cs.name, "added": len(wanted - set(current)),
                                            "removed": len(set(current) - wanted), "mode": cs.mode.value})
    await db.commit()
    return (await _set_responses(db, [cs]))[0]


@router.delete("/channel-sets/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel_set(
    workspace_id: uuid.UUID, set_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_MANAGE_TELEGRAM)
    cs = await _set_or_404(db, workspace_id, set_id)
    scheduled = await db.scalar(select(func.count()).select_from(ContentItem).where(
        ContentItem.channel_set_id == cs.id, ContentItem.status.in_([ContentStatus.SCHEDULED, ContentStatus.PUBLISHING])))
    if scheduled:
        raise ApiError(409, "CHANNEL_SET_IN_USE", f"{scheduled} scheduled post(s) target this set. Unschedule or retarget them first.", count=scheduled)
    await db.delete(cs)
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="channel_set.deleted",
                                  entity_type="channel_set", entity_id=set_id, metadata={"name": cs.name})
    await db.commit()
