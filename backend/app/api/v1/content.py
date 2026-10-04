from __future__ import annotations

import base64
import difflib
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_workspace_member
from app.api.v1.jobs import JobResponse
from app.core.rbac import CAN_APPROVE_CONTENT, CAN_EDIT_CONTENT, require_role
from app.models.content import ContentItem, ContentRevision, ContentSeries
from app.models.cost import AIRequest
from app.models.distribution import DistributionBatch, Publication
from app.models.enums import (
    AIOperation,
    AIRequestStatus,
    ContentStatus,
    JobType,
    PublicationStatus,
    WorkspaceRole,
)
from app.models.identity import User, WorkspaceMember
from app.models.media import MediaAsset
from app.models.scheduling import Schedule, ScheduleRule
from app.models.telegram import ChannelSet, ChannelSetMember
from app.services.ai.factory import get_image_provider, get_text_provider
from app.services.ai.service import AIService
from app.services.audit.service import AuditService
from app.services.content.context import PromptContextBuilder
from app.services.content.html_sanitizer import sanitize_telegram_html, strip_to_plain_text
from app.services.content.series_service import SeriesService
from app.services.content.service import ContentService, InvalidTransitionError
from app.services.content.transforms import EDITABLE_STATUSES, OPERATIONS, latest_revision
from app.services.costs.service import CostService
from app.services.jobs.service import JobService, dispatch
from app.services.notifications.service import NotificationService
from app.services.publishing.distribution_service import DistributionService
from app.services.realtime.events import publish_event
from app.services.scheduling.service import ScheduleService
from app.services.settings.service import cta_defaults

router = APIRouter(prefix="/workspaces/{workspace_id}/content", tags=["content"])


def _content_service(db: AsyncSession) -> ContentService:
    return ContentService(db, AIService(db, get_text_provider(), get_image_provider()))


# ---------------------------------------------------------------- schemas


class ContentResponse(BaseModel):
    id: uuid.UUID
    status: str
    topic: str
    category: str
    angle: str
    title: str
    plain_text: str
    telegram_html: str
    cta_key: str | None
    tags: list[str]
    sources: list[str]
    risk_flags: list[str]
    duplicate_score: float | None
    requires_review: bool
    image_prompt: str
    media_asset_id: uuid.UUID | None
    channel_set_id: uuid.UUID | None
    series_id: uuid.UUID | None
    schedule_id: uuid.UUID | None
    tone_profile_id: uuid.UUID | None
    source_item_id: uuid.UUID | None
    scheduled_at: datetime | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    created_by_user_id: uuid.UUID | None
    latest_revision_id: uuid.UUID | None = None
    ai_cost_rub: Decimal = Decimal(0)

    @classmethod
    def from_model(cls, item: ContentItem, **extra) -> ContentResponse:
        def _list(raw: str | None) -> list[str]:
            try:
                value = json.loads(raw or "[]")
                return [str(v) for v in value] if isinstance(value, list) else []
            except json.JSONDecodeError:
                return []

        return cls(
            id=item.id, status=item.status.value, topic=item.topic, category=item.category, angle=item.angle,
            title=item.title, plain_text=item.plain_text, telegram_html=item.telegram_html, cta_key=item.cta_key,
            tags=_list(item.tags_json), sources=_list(item.sources_json), risk_flags=_list(item.risk_flags_json),
            duplicate_score=item.duplicate_score, requires_review=item.requires_review,
            image_prompt=item.image_prompt, media_asset_id=item.media_asset_id,
            channel_set_id=item.channel_set_id, series_id=item.series_id, schedule_id=item.schedule_id,
            tone_profile_id=item.tone_profile_id, source_item_id=item.source_item_id,
            scheduled_at=item.scheduled_at, published_at=item.published_at, created_at=item.created_at,
            updated_at=item.updated_at, created_by_user_id=item.created_by_user_id, **extra,
        )


class ContentListItem(BaseModel):
    id: uuid.UUID
    status: str
    title: str
    topic: str
    category: str
    excerpt: str
    channel_set_id: uuid.UUID | None
    channel_set_name: str | None
    series_id: uuid.UUID | None
    targets: int
    published_count: int
    failed_count: int
    views: int
    ai_cost_rub: Decimal
    scheduled_at: datetime | None
    published_at: datetime | None
    created_at: datetime
    author_id: uuid.UUID | None
    author_name: str | None
    media_asset_id: uuid.UUID | None
    duplicate_score: float | None
    requires_review: bool


class ContentPage(BaseModel):
    items: list[ContentListItem]
    next_cursor: str | None


class GenerateRequest(BaseModel):
    instruction: str = Field(default="", max_length=4000)
    channel_set_id: uuid.UUID | None = None
    tone_profile_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    source_item_id: uuid.UUID | None = None
    topic: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def _something_to_write_about(self):
        if not (self.instruction.strip() or self.topic.strip() or self.series_id or self.source_item_id):
            raise ValueError("Describe what to write about, or pick a series or an idea.")
        return self


class GenerateResponse(BaseModel):
    content: ContentResponse
    job: JobResponse


class CreateRequest(BaseModel):
    title: str = Field(default="", max_length=300)
    telegram_html: str = Field(default="", max_length=8000)
    channel_set_id: uuid.UUID | None = None
    category: str = Field(default="", max_length=100)


class EditRequest(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    telegram_html: str | None = Field(default=None, max_length=8000)
    category: str | None = Field(default=None, max_length=100)
    cta_key: str | None = None
    channel_set_id: uuid.UUID | None = None
    tone_profile_id: uuid.UUID | None = None
    media_asset_id: uuid.UUID | None = None
    clear_media: bool = False
    base_revision_id: uuid.UUID | None = None  # optimistic concurrency for autosave


class TransformRequest(BaseModel):
    operation: str
    selection: str = Field(default="", max_length=4000)
    instructions: str = Field(default="", max_length=1000)
    tone_profile_id: uuid.UUID | None = None
    base_revision_id: uuid.UUID | None = None


class ScheduleRequest(BaseModel):
    scheduled_at: datetime | None = None
    schedule_id: uuid.UUID | None = None  # "next free slot of this schedule"

    @model_validator(mode="after")
    def _one_of(self):
        if (self.scheduled_at is None) == (self.schedule_id is None):
            raise ValueError("Provide either scheduled_at or schedule_id.")
        return self


class RescheduleRequest(BaseModel):
    scheduled_at: datetime


class RevisionResponse(BaseModel):
    id: uuid.UUID
    version: int
    action: str
    is_ai: bool
    author_id: uuid.UUID | None
    author_name: str | None
    created_at: datetime
    title: str
    telegram_html: str
    cost_rub: Decimal | None
    prompt_tokens: int | None
    completion_tokens: int | None
    diff: list[dict]


class CostLine(BaseModel):
    operation: str
    count: int
    failed: int
    prompt_tokens: int
    completion_tokens: int
    cost_rub: Decimal


class CostBreakdown(BaseModel):
    lines: list[CostLine]
    text_cost_rub: Decimal
    image_cost_rub: Decimal
    total_rub: Decimal


class CalendarEntry(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    category: str
    at: datetime
    kind: str  # scheduled|published
    channel_set_id: uuid.UUID | None
    channel_set_name: str | None
    media_asset_id: uuid.UUID | None
    targets: int
    published_count: int
    failed_count: int


class SlotEntry(BaseModel):
    schedule_id: uuid.UUID
    schedule_name: str
    channel_set_id: uuid.UUID | None
    at: datetime


class CalendarResponse(BaseModel):
    entries: list[CalendarEntry]
    free_slots: list[SlotEntry]


# ---------------------------------------------------------------- helpers


async def _get_or_404(db: AsyncSession, workspace_id: uuid.UUID, content_id: uuid.UUID) -> ContentItem:
    item = await db.get(ContentItem, content_id)
    if not item or item.workspace_id != workspace_id or item.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content item not found")
    return item


async def _check_refs(db: AsyncSession, workspace_id: uuid.UUID, **refs) -> None:
    """Every referenced object must belong to the same workspace."""
    from app.models.knowledge import ToneOfVoiceProfile
    from app.models.sources import SourceItem

    models = {
        "channel_set_id": (ChannelSet, "Channel set"), "tone_profile_id": (ToneOfVoiceProfile, "Tone profile"),
        "series_id": (ContentSeries, "Series"), "source_item_id": (SourceItem, "Idea"),
        "media_asset_id": (MediaAsset, "Media"), "schedule_id": (Schedule, "Schedule"),
    }
    for field, value in refs.items():
        if value is None:
            continue
        model, label = models[field]
        obj = await db.get(model, value)
        if obj is None or obj.workspace_id != workspace_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found")


async def _transition(fn, item: ContentItem) -> ContentItem:
    try:
        return await fn(item)
    except InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


async def _ai_cost(db: AsyncSession, content_id: uuid.UUID) -> Decimal:
    value = await db.scalar(
        select(func.coalesce(func.sum(AIRequest.total_cost_rub), 0)).where(AIRequest.content_item_id == content_id)
    )
    return Decimal(value or 0)


async def _full(db: AsyncSession, item: ContentItem) -> ContentResponse:
    latest = await latest_revision(db, item.id)
    return ContentResponse.from_model(
        item, latest_revision_id=latest.id if latest else None, ai_cost_rub=await _ai_cost(db, item.id)
    )


def _encode_cursor(stamp: datetime, item_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{stamp.isoformat()}|{item_id}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        stamp, item_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(stamp), uuid.UUID(item_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid cursor") from exc


async def _delivery_stats(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    from app.models.analytics import PostMetricSnapshot

    stats: dict[uuid.UUID, dict[str, int]] = {i: {"targets": 0, "published": 0, "failed": 0, "views": 0} for i in ids}
    if not ids:
        return stats
    rows = await db.execute(
        select(DistributionBatch.content_item_id, Publication.status, func.count())
        .join(Publication, Publication.batch_id == DistributionBatch.id)
        .where(DistributionBatch.content_item_id.in_(ids))
        .group_by(DistributionBatch.content_item_id, Publication.status)
    )
    for content_id, pub_status, n in rows.all():
        s = stats[content_id]
        s["targets"] += n
        if pub_status == PublicationStatus.SUCCESS:
            s["published"] += n
        elif pub_status == PublicationStatus.FAILED:
            s["failed"] += n
    latest = (
        select(PostMetricSnapshot.publication_id, func.max(PostMetricSnapshot.captured_at).label("at"))
        .group_by(PostMetricSnapshot.publication_id)
        .subquery()
    )
    view_rows = await db.execute(
        select(DistributionBatch.content_item_id, func.sum(PostMetricSnapshot.views))
        .join(Publication, Publication.batch_id == DistributionBatch.id)
        .join(latest, latest.c.publication_id == Publication.id)
        .join(PostMetricSnapshot, and_(PostMetricSnapshot.publication_id == Publication.id,
                                       PostMetricSnapshot.captured_at == latest.c.at))
        .where(DistributionBatch.content_item_id.in_(ids))
        .group_by(DistributionBatch.content_item_id)
    )
    for content_id, views in view_rows.all():
        stats[content_id]["views"] = int(views or 0)
    return stats


async def _audit(db: AsyncSession, workspace_id: uuid.UUID, user: User, action: str, item: ContentItem, **meta) -> None:
    await AuditService(db).record(
        workspace_id=workspace_id, actor_user_id=user.id, action=action, entity_type="content",
        entity_id=item.id, metadata={"title": item.title[:120], **meta},
    )


# ---------------------------------------------------------------- list / read


@router.get("", response_model=ContentPage)
async def list_content(
    workspace_id: uuid.UUID,
    status_filter: list[ContentStatus] | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=200),
    category: str | None = None,
    channel_set_id: uuid.UUID | None = None,
    series_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    member: WorkspaceMember = Depends(get_workspace_member),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ContentItem).where(ContentItem.workspace_id == workspace_id, ContentItem.deleted_at.is_(None))
    if status_filter:
        stmt = stmt.where(ContentItem.status.in_(status_filter))
    if q:
        pattern = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(ContentItem.title).like(pattern), func.lower(ContentItem.plain_text).like(pattern),
                              func.lower(ContentItem.topic).like(pattern)))
    if category:
        stmt = stmt.where(ContentItem.category == category)
    if channel_set_id:
        stmt = stmt.where(ContentItem.channel_set_id == channel_set_id)
    if series_id:
        stmt = stmt.where(ContentItem.series_id == series_id)
    if cursor:
        stamp, last_id = _decode_cursor(cursor)
        stmt = stmt.where(or_(ContentItem.created_at < stamp, and_(ContentItem.created_at == stamp, ContentItem.id < last_id)))
    rows = (await db.execute(stmt.order_by(ContentItem.created_at.desc(), ContentItem.id.desc()).limit(limit + 1))).scalars().all()
    page = rows[:limit]
    ids = [i.id for i in page]

    costs = dict((await db.execute(
        select(AIRequest.content_item_id, func.coalesce(func.sum(AIRequest.total_cost_rub), 0))
        .where(AIRequest.content_item_id.in_(ids)).group_by(AIRequest.content_item_id)
    )).all()) if ids else {}
    stats = await _delivery_stats(db, ids)
    set_ids = {i.channel_set_id for i in page if i.channel_set_id}
    set_names = dict((await db.execute(select(ChannelSet.id, ChannelSet.name).where(ChannelSet.id.in_(set_ids)))).all()) if set_ids else {}
    author_ids = {i.created_by_user_id for i in page if i.created_by_user_id}
    authors = dict((await db.execute(select(User.id, User.full_name).where(User.id.in_(author_ids)))).all()) if author_ids else {}

    items = [
        ContentListItem(
            id=i.id, status=i.status.value, title=i.title, topic=i.topic, category=i.category,
            excerpt=(i.plain_text or "")[:180], channel_set_id=i.channel_set_id,
            channel_set_name=set_names.get(i.channel_set_id), series_id=i.series_id,
            targets=stats[i.id]["targets"], published_count=stats[i.id]["published"],
            failed_count=stats[i.id]["failed"], views=stats[i.id]["views"],
            ai_cost_rub=Decimal(costs.get(i.id, 0) or 0), scheduled_at=i.scheduled_at, published_at=i.published_at,
            created_at=i.created_at, author_id=i.created_by_user_id,
            author_name=authors.get(i.created_by_user_id) if i.created_by_user_id else "Autopilot",
            media_asset_id=i.media_asset_id, duplicate_score=i.duplicate_score, requires_review=i.requires_review,
        )
        for i in page
    ]
    return ContentPage(items=items, next_cursor=_encode_cursor(page[-1].created_at, page[-1].id) if len(rows) > limit else None)


@router.get("/calendar", response_model=CalendarResponse)
async def calendar(
    workspace_id: uuid.UUID,
    start: datetime,
    end: datetime,
    channel_set_id: uuid.UUID | None = None,
    include_slots: bool = True,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: AsyncSession = Depends(get_db),
):
    if end <= start or end - start > timedelta(days=62):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Calendar range must be positive and at most 62 days")
    stmt = select(ContentItem).where(
        ContentItem.workspace_id == workspace_id,
        ContentItem.deleted_at.is_(None),
        or_(and_(ContentItem.scheduled_at >= start, ContentItem.scheduled_at < end),
            and_(ContentItem.published_at >= start, ContentItem.published_at < end)),
    )
    if channel_set_id:
        stmt = stmt.where(ContentItem.channel_set_id == channel_set_id)
    items = (await db.execute(stmt)).scalars().all()
    stats = await _delivery_stats(db, [i.id for i in items])
    set_ids = {i.channel_set_id for i in items if i.channel_set_id}
    names = dict((await db.execute(select(ChannelSet.id, ChannelSet.name).where(ChannelSet.id.in_(set_ids)))).all()) if set_ids else {}
    entries = []
    for i in items:
        published = i.status in (ContentStatus.PUBLISHED, ContentStatus.PARTIALLY_PUBLISHED) and i.published_at
        at = i.published_at if published else i.scheduled_at
        if at is None:
            continue
        entries.append(CalendarEntry(
            id=i.id, title=i.title or i.topic or "Untitled", status=i.status.value, category=i.category, at=at,
            kind="published" if published else "scheduled", channel_set_id=i.channel_set_id,
            channel_set_name=names.get(i.channel_set_id), media_asset_id=i.media_asset_id,
            targets=stats[i.id]["targets"], published_count=stats[i.id]["published"], failed_count=stats[i.id]["failed"],
        ))
    entries.sort(key=lambda e: e.at)

    slots: list[SlotEntry] = []
    if include_slots:
        now = datetime.now(UTC)
        sched_stmt = select(Schedule).where(Schedule.workspace_id == workspace_id, Schedule.is_paused.is_(False))
        if channel_set_id:
            sched_stmt = sched_stmt.where(Schedule.channel_set_id == channel_set_id)
        service = ScheduleService()
        for schedule in (await db.execute(sched_stmt)).scalars().all():
            rules = (await db.execute(select(ScheduleRule).where(ScheduleRule.schedule_id == schedule.id))).scalars().all()
            taken = [e.at for e in entries if e.channel_set_id == schedule.channel_set_id]
            gap = timedelta(minutes=max(1, schedule.min_interval_minutes or 0))
            for at in service.upcoming(schedule, rules, after=max(start, now), until=end, limit=200):
                if all(abs(at - t) >= gap for t in taken):
                    slots.append(SlotEntry(schedule_id=schedule.id, schedule_name=schedule.name,
                                           channel_set_id=schedule.channel_set_id, at=at))
    return CalendarResponse(entries=entries, free_slots=slots)


@router.get("/{content_id}", response_model=ContentResponse)
async def get_content(
    workspace_id: uuid.UUID, content_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    return await _full(db, await _get_or_404(db, workspace_id, content_id))


@router.get("/{content_id}/context")
async def get_active_context(
    workspace_id: uuid.UUID, content_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    """Which tone profile and series apply — shown in Content Studio."""
    item = await _get_or_404(db, workspace_id, content_id)
    profile, source = await PromptContextBuilder(db).resolve_tone(item)
    series = None
    if item.series_id:
        s = await db.get(ContentSeries, item.series_id)
        if s:
            progress = await SeriesService(db).progress(s)
            series = {"id": str(s.id), "title": s.title, "next_label": progress["next_label"]}
    return {
        "tone": {"id": str(profile.id), "name": profile.name, "source": source} if profile else None,
        "series": series,
    }


# ---------------------------------------------------------------- create / generate / edit


@router.post("", response_model=ContentResponse, status_code=status.HTTP_201_CREATED)
async def create_content(
    workspace_id: uuid.UUID, payload: CreateRequest,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manual post (no AI)."""
    require_role(member.role, CAN_EDIT_CONTENT)
    await _check_refs(db, workspace_id, channel_set_id=payload.channel_set_id)
    html = sanitize_telegram_html(payload.telegram_html)
    item = ContentItem(
        workspace_id=workspace_id, created_by_user_id=user.id, status=ContentStatus.DRAFT, title=payload.title,
        telegram_html=html, plain_text=strip_to_plain_text(html), channel_set_id=payload.channel_set_id,
        category=payload.category,
    )
    db.add(item)
    await db.flush()
    db.add(ContentRevision(content_item_id=item.id, edited_by_user_id=user.id, action="created",
                           title=item.title, plain_text=item.plain_text, telegram_html=item.telegram_html))
    await _audit(db, workspace_id, user, "content.created", item)
    await db.commit()
    return await _full(db, item)


@router.post("/generate", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate(
    workspace_id: uuid.UUID, payload: GenerateRequest,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    await _check_refs(db, workspace_id, channel_set_id=payload.channel_set_id, tone_profile_id=payload.tone_profile_id,
                      series_id=payload.series_id, source_item_id=payload.source_item_id)
    costs = CostService(db)
    # Fail fast with a clear message instead of queuing a job that can't run.
    await costs.assert_ai_allowed(workspace_id, costs.estimate_text_cost(len(payload.instruction) + 6000, 1200))

    topic, instruction = payload.topic, payload.instruction
    channel_set_id, tone_profile_id = payload.channel_set_id, payload.tone_profile_id
    series = None
    if payload.series_id:
        series = await db.get(ContentSeries, payload.series_id)
        if series.status in ("PAUSED", "COMPLETED"):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Series is {series.status.lower()}")
        progress = await SeriesService(db).progress(series)
        topic = topic or progress["next_topic"] or ""
        channel_set_id = channel_set_id or series.channel_set_id
    if payload.source_item_id:
        from app.models.sources import SourceItem

        idea = await db.get(SourceItem, payload.source_item_id)
        topic = topic or idea.title
        instruction = (
            f"{instruction}\n\nBase the post on this source (cite it in sources): {idea.title}\n"
            f"{idea.summary[:1500]}\nURL: {idea.url}"
        ).strip()

    item = await _content_service(db).create_generation_request(
        workspace_id=workspace_id, user_id=user.id, channel_set_id=channel_set_id, tone_profile_id=tone_profile_id,
        series_id=payload.series_id, source_item_id=payload.source_item_id, topic=topic,
    )
    if series is not None:
        await SeriesService(db).attach(series, item)
        item.category = item.category or series.category
    job = await JobService(db).create(
        workspace_id=workspace_id, job_type=JobType.AI_GENERATE_POST,
        payload={"content_id": str(item.id), "instruction": instruction},
        entity_type="content", entity_id=item.id,
        summary=f"Generate: {(topic or instruction)[:120]}", created_by_user_id=user.id, max_attempts=1,
    )
    await _audit(db, workspace_id, user, "content.generation_requested", item, job_id=str(job.id))
    await db.commit()
    await dispatch(job)
    await db.refresh(item)
    await db.refresh(job)
    return GenerateResponse(content=await _full(db, item), job=JobResponse.from_model(job))


@router.patch("/{content_id}", response_model=ContentResponse)
async def edit_content(
    workspace_id: uuid.UUID, content_id: uuid.UUID, payload: EditRequest,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    item = await _get_or_404(db, workspace_id, content_id)
    if item.status not in EDITABLE_STATUSES and item.status != ContentStatus.SCHEDULED:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Content is {item.status.value.lower()} and can't be edited")
    latest = await latest_revision(db, item.id)
    if payload.base_revision_id and latest and latest.id != payload.base_revision_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This post was changed elsewhere (another tab, a teammate or an AI action). Reload to see the latest version.",
        )
    await _check_refs(db, workspace_id, channel_set_id=payload.channel_set_id, tone_profile_id=payload.tone_profile_id,
                      media_asset_id=payload.media_asset_id)

    text_changed = False
    if payload.title is not None and payload.title != item.title:
        item.title = payload.title
        text_changed = True
    if payload.telegram_html is not None:
        html = sanitize_telegram_html(payload.telegram_html)
        if html != item.telegram_html:
            item.telegram_html = html
            item.plain_text = strip_to_plain_text(html)
            text_changed = True
    for field in ("category", "cta_key", "channel_set_id", "tone_profile_id", "media_asset_id"):
        value = getattr(payload, field)
        if value is not None:
            setattr(item, field, value)
    if payload.clear_media:
        item.media_asset_id = None

    revision = None
    if text_changed:
        revision = ContentRevision(content_item_id=item.id, edited_by_user_id=user.id, action="manual_edit",
                                   title=item.title, plain_text=item.plain_text, telegram_html=item.telegram_html)
        db.add(revision)
        if item.status == ContentStatus.APPROVED:
            # An approved post edited afterwards needs approval again.
            item.status = ContentStatus.PENDING_APPROVAL
        await _audit(db, workspace_id, user, "content.edited", item)
    await db.flush()
    if item.status == ContentStatus.SCHEDULED and text_changed:
        # Keep the not-yet-sent batch in sync with the new text.
        channel_set = await db.get(ChannelSet, item.channel_set_id) if item.channel_set_id else None
        if channel_set:
            await DistributionService(db).prepare_batch(
                content_item=item, mode=channel_set.mode, workspace_cta_defaults=await cta_defaults(db, workspace_id)
            )
    await db.commit()
    await publish_event(workspace_id, "content.updated", {"content_id": str(item.id),
                                                          "revision_id": str(revision.id) if revision else None})
    return await _full(db, item)


@router.post("/{content_id}/transform", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def transform(
    workspace_id: uuid.UUID, content_id: uuid.UUID, payload: TransformRequest,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    item = await _get_or_404(db, workspace_id, content_id)
    if payload.operation not in OPERATIONS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown operation {payload.operation!r}")
    if item.status not in EDITABLE_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Content is {item.status.value.lower()} and can't be edited")
    if OPERATIONS[payload.operation][2] and not payload.selection.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Select the fragment to regenerate first.")
    await _check_refs(db, workspace_id, tone_profile_id=payload.tone_profile_id)
    jobs = JobService(db)
    active = await jobs.active_for_entity("content", item.id)
    if active is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Another AI action is already running for this post.")
    costs = CostService(db)
    await costs.assert_ai_allowed(workspace_id, costs.estimate_text_cost(len(item.telegram_html) + 6000, 1200))
    latest = await latest_revision(db, item.id)
    job = await jobs.create(
        workspace_id=workspace_id, job_type=JobType.AI_REWRITE,
        payload={
            "content_id": str(item.id), "operation": payload.operation, "selection": payload.selection,
            "instructions": payload.instructions,
            "tone_profile_id": str(payload.tone_profile_id) if payload.tone_profile_id else None,
            "base_revision_id": str(payload.base_revision_id or (latest.id if latest else "")) or None,
        },
        entity_type="content", entity_id=item.id,
        summary=f"{payload.operation.replace('_', ' ').capitalize()}: {item.title[:100]}",
        created_by_user_id=user.id, max_attempts=1,
    )
    await db.commit()
    await dispatch(job)
    await db.refresh(job)
    return JobResponse.from_model(job)


# ---------------------------------------------------------------- versions


@router.get("/{content_id}/revisions", response_model=list[RevisionResponse])
async def list_revisions(
    workspace_id: uuid.UUID, content_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    await _get_or_404(db, workspace_id, content_id)
    revisions = (await db.execute(
        select(ContentRevision).where(ContentRevision.content_item_id == content_id)
        .order_by(ContentRevision.created_at, ContentRevision.id)
    )).scalars().all()
    req_ids = [r.ai_request_id for r in revisions if r.ai_request_id]
    requests = {r.id: r for r in (await db.execute(select(AIRequest).where(AIRequest.id.in_(req_ids)))).scalars().all()} if req_ids else {}
    user_ids = {r.edited_by_user_id for r in revisions if r.edited_by_user_id}
    names = dict((await db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids)))).all()) if user_ids else {}

    out: list[RevisionResponse] = []
    previous = ""
    for n, r in enumerate(revisions, start=1):
        req = requests.get(r.ai_request_id) if r.ai_request_id else None
        diff = [
            {"op": op, "text": text}
            for op, text in _word_diff(previous, r.plain_text or strip_to_plain_text(r.telegram_html))
        ]
        previous = r.plain_text or strip_to_plain_text(r.telegram_html)
        out.append(RevisionResponse(
            id=r.id, version=n, action=r.action, is_ai=req is not None or r.action == AIOperation.GENERATE_POST.value,
            author_id=r.edited_by_user_id,
            author_name=names.get(r.edited_by_user_id) if r.edited_by_user_id else "Autopilot",
            created_at=r.created_at, title=r.title, telegram_html=r.telegram_html,
            cost_rub=req.total_cost_rub if req else None, prompt_tokens=req.prompt_tokens if req else None,
            completion_tokens=req.completion_tokens if req else None, diff=diff,
        ))
    return list(reversed(out))


def _word_diff(old: str, new: str) -> list[tuple[str, str]]:
    a, b = old.split(" "), new.split(" ")
    out: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            out.append(("equal", " ".join(a[i1:i2])))
        else:
            if i2 > i1:
                out.append(("delete", " ".join(a[i1:i2])))
            if j2 > j1:
                out.append(("insert", " ".join(b[j1:j2])))
    return out


@router.post("/{content_id}/revisions/{revision_id}/restore", response_model=ContentResponse)
async def restore_revision(
    workspace_id: uuid.UUID, content_id: uuid.UUID, revision_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Restoring creates a new version with the old text — history is never rewritten."""
    require_role(member.role, CAN_EDIT_CONTENT)
    item = await _get_or_404(db, workspace_id, content_id)
    if item.status not in EDITABLE_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Content is {item.status.value.lower()} and can't be edited")
    rev = await db.get(ContentRevision, revision_id)
    if rev is None or rev.content_item_id != item.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    item.title, item.telegram_html = rev.title, sanitize_telegram_html(rev.telegram_html)
    item.plain_text = strip_to_plain_text(item.telegram_html)
    if item.status == ContentStatus.APPROVED:
        item.status = ContentStatus.PENDING_APPROVAL
    db.add(ContentRevision(content_item_id=item.id, edited_by_user_id=user.id, action="restore",
                           title=item.title, plain_text=item.plain_text, telegram_html=item.telegram_html))
    await _audit(db, workspace_id, user, "content.version_restored", item, revision_id=str(rev.id))
    await db.commit()
    await publish_event(workspace_id, "content.updated", {"content_id": str(item.id)})
    return await _full(db, item)


@router.get("/{content_id}/costs", response_model=CostBreakdown)
async def content_costs(
    workspace_id: uuid.UUID, content_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    await _get_or_404(db, workspace_id, content_id)
    rows = (await db.execute(select(AIRequest).where(AIRequest.content_item_id == content_id))).scalars().all()
    by_op: dict[str, CostLine] = {}
    text = image = Decimal(0)
    for r in rows:
        line = by_op.setdefault(r.operation.value, CostLine(operation=r.operation.value, count=0, failed=0,
                                                            prompt_tokens=0, completion_tokens=0, cost_rub=Decimal(0)))
        line.count += 1
        line.failed += 1 if r.status != AIRequestStatus.SUCCESS else 0
        line.prompt_tokens += r.prompt_tokens
        line.completion_tokens += r.completion_tokens
        line.cost_rub += Decimal(r.total_cost_rub)
        if r.operation == AIOperation.GENERATE_IMAGE:
            image += Decimal(r.total_cost_rub)
        else:
            text += Decimal(r.total_cost_rub)
    return CostBreakdown(lines=sorted(by_op.values(), key=lambda line: -line.cost_rub), text_cost_rub=text,
                         image_cost_rub=image, total_rub=text + image)


# ---------------------------------------------------------------- workflow


@router.post("/{content_id}/submit", response_model=ContentResponse)
async def submit_for_approval(
    workspace_id: uuid.UUID, content_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    item = await _get_or_404(db, workspace_id, content_id)
    await _transition(_content_service(db).submit_for_approval, item)
    await _audit(db, workspace_id, user, "content.submitted", item)
    await NotificationService(db).notify(
        workspace_id=workspace_id, kind="approval.required",
        message=f"“{item.title or 'Untitled'}” is waiting for approval.",
        metadata={"content_id": str(item.id)}, min_role=WorkspaceRole.APPROVER,
        dedupe_key=f"approval:{item.id}", dedupe_window=timedelta(hours=6),
    )
    await db.commit()
    await publish_event(workspace_id, "content.updated", {"content_id": str(item.id), "status": item.status.value})
    return await _full(db, item)


@router.post("/{content_id}/approve", response_model=ContentResponse)
async def approve(
    workspace_id: uuid.UUID, content_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_APPROVE_CONTENT)
    item = await _get_or_404(db, workspace_id, content_id)
    if item.status == ContentStatus.DRAFT:
        await _transition(_content_service(db).submit_for_approval, item)
    await _transition(_content_service(db).approve, item)
    await _audit(db, workspace_id, user, "content.approved", item)
    await db.commit()
    await publish_event(workspace_id, "content.approved", {"content_id": str(item.id)})
    return await _full(db, item)


@router.post("/{content_id}/reject", response_model=ContentResponse)
async def reject(
    workspace_id: uuid.UUID, content_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_APPROVE_CONTENT)
    item = await _get_or_404(db, workspace_id, content_id)
    await _transition(_content_service(db).reject, item)
    await _audit(db, workspace_id, user, "content.rejected", item)
    await db.commit()
    await publish_event(workspace_id, "content.updated", {"content_id": str(item.id), "status": item.status.value})
    return await _full(db, item)


async def _apply_schedule(db: AsyncSession, workspace_id: uuid.UUID, item: ContentItem, at: datetime) -> None:
    if item.channel_set_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Choose a target channel set before scheduling.")
    members = await db.scalar(select(func.count()).select_from(ChannelSetMember)
                              .where(ChannelSetMember.channel_set_id == item.channel_set_id))
    if not members:
        raise HTTPException(status.HTTP_409_CONFLICT, "The target channel set has no channels.")
    channel_set = await db.get(ChannelSet, item.channel_set_id)
    await DistributionService(db).prepare_batch(
        content_item=item, mode=channel_set.mode, workspace_cta_defaults=await cta_defaults(db, workspace_id)
    )
    item.scheduled_at = at


@router.post("/{content_id}/schedule", response_model=ContentResponse)
async def schedule_content(
    workspace_id: uuid.UUID, content_id: uuid.UUID, payload: ScheduleRequest,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_APPROVE_CONTENT)
    item = await _get_or_404(db, workspace_id, content_id)
    now = datetime.now(UTC)
    if payload.schedule_id:
        await _check_refs(db, workspace_id, schedule_id=payload.schedule_id)
        schedule = await db.get(Schedule, payload.schedule_id)
        if schedule.channel_set_id and not item.channel_set_id:
            item.channel_set_id = schedule.channel_set_id
        rules = (await db.execute(select(ScheduleRule).where(ScheduleRule.schedule_id == schedule.id))).scalars().all()
        occupied = [r[0] for r in (await db.execute(
            select(ContentItem.scheduled_at).where(
                ContentItem.workspace_id == workspace_id, ContentItem.channel_set_id == item.channel_set_id,
                ContentItem.status == ContentStatus.SCHEDULED, ContentItem.id != item.id,
            ))).all() if r[0]]
        at = ScheduleService().next_free_slot(schedule, rules, after=now, occupied=occupied)
        if at is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "This schedule has no free slots in the next 120 days.")
        item.schedule_id = schedule.id
    else:
        at = payload.scheduled_at if payload.scheduled_at.tzinfo else payload.scheduled_at.replace(tzinfo=UTC)
        if at < now - timedelta(minutes=1):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pick a time in the future.")
    await _transition(_content_service(db).schedule_only_status, item)
    await _apply_schedule(db, workspace_id, item, at)
    await _audit(db, workspace_id, user, "content.scheduled", item, scheduled_at=at.isoformat())
    await db.commit()
    await publish_event(workspace_id, "content.scheduled", {"content_id": str(item.id), "scheduled_at": at.isoformat()})
    return await _full(db, item)


@router.patch("/{content_id}/schedule", response_model=ContentResponse)
async def reschedule_content(
    workspace_id: uuid.UUID, content_id: uuid.UUID, payload: RescheduleRequest,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Calendar drag & drop."""
    require_role(member.role, CAN_APPROVE_CONTENT)
    item = await _get_or_404(db, workspace_id, content_id)
    if item.status != ContentStatus.SCHEDULED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only scheduled posts can be moved.")
    at = payload.scheduled_at if payload.scheduled_at.tzinfo else payload.scheduled_at.replace(tzinfo=UTC)
    if at < datetime.now(UTC) - timedelta(minutes=1):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Can't move a post into the past.")
    previous = item.scheduled_at
    item.scheduled_at = at
    await _audit(db, workspace_id, user, "content.rescheduled", item,
                 previous=previous.isoformat() if previous else None, scheduled_at=at.isoformat())
    await db.commit()
    await publish_event(workspace_id, "content.scheduled", {"content_id": str(item.id), "scheduled_at": at.isoformat()})
    return await _full(db, item)


@router.delete("/{content_id}/schedule", response_model=ContentResponse)
async def unschedule_content(
    workspace_id: uuid.UUID, content_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_APPROVE_CONTENT)
    item = await _get_or_404(db, workspace_id, content_id)
    if item.status != ContentStatus.SCHEDULED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Post is not scheduled.")
    item.status = ContentStatus.APPROVED
    item.scheduled_at = None
    await _audit(db, workspace_id, user, "content.unscheduled", item)
    await db.commit()
    await publish_event(workspace_id, "content.updated", {"content_id": str(item.id), "status": item.status.value})
    return await _full(db, item)


@router.post("/{content_id}/publish-now", response_model=ContentResponse)
async def publish_now(
    workspace_id: uuid.UUID, content_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_APPROVE_CONTENT)
    item = await _get_or_404(db, workspace_id, content_id)
    if item.status != ContentStatus.SCHEDULED:
        await _transition(_content_service(db).schedule_only_status, item)
    now = datetime.now(UTC)
    await _apply_schedule(db, workspace_id, item, now)
    await _audit(db, workspace_id, user, "content.publish_now", item)
    await db.commit()
    await publish_event(workspace_id, "content.scheduled", {"content_id": str(item.id), "scheduled_at": now.isoformat()})
    return await _full(db, item)


@router.delete("/{content_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_content(
    workspace_id: uuid.UUID, content_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft delete. Anything already (partly) published is kept for history — archive it instead."""
    require_role(member.role, CAN_EDIT_CONTENT)
    item = await _get_or_404(db, workspace_id, content_id)
    if item.status in (ContentStatus.PUBLISHING, ContentStatus.PUBLISHED, ContentStatus.PARTIALLY_PUBLISHED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Published posts can't be deleted; archive them instead.")
    item.deleted_at = datetime.now(UTC)
    if item.status == ContentStatus.SCHEDULED:
        item.status = ContentStatus.ARCHIVED
    await _audit(db, workspace_id, user, "content.deleted", item)
    await db.commit()
    await publish_event(workspace_id, "content.updated", {"content_id": str(item.id), "deleted": True})


@router.post("/{content_id}/archive", response_model=ContentResponse)
async def archive(
    workspace_id: uuid.UUID, content_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    item = await _get_or_404(db, workspace_id, content_id)
    await _transition(_content_service(db).archive, item)
    await _audit(db, workspace_id, user, "content.archived", item)
    await db.commit()
    return await _full(db, item)
