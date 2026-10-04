from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_workspace_member
from app.core.errors import ApiError
from app.models.analytics import PostMetricSnapshot
from app.models.content import ContentItem
from app.models.cost import AIRequest
from app.models.distribution import DistributionBatch, Publication
from app.models.enums import (
    AIOperation,
    AIRequestStatus,
    ContentStatus,
    JobStatus,
    PublicationStatus,
    TelegramAccountStatus,
)
from app.models.identity import WorkspaceMember
from app.models.ops import Job
from app.models.telegram import ChannelSet, TelegramAccount, TelegramChannel
from app.services.ai.factory import get_image_provider, get_text_provider
from app.services.analytics.service import AnalyticsService
from app.services.costs.service import CostService
from app.services.system.health import readiness

router = APIRouter(prefix="/workspaces/{workspace_id}/analytics", tags=["analytics"])

TRANSFORM_OPS = [AIOperation.REWRITE, AIOperation.SHORTEN, AIOperation.EXPAND, AIOperation.CHANGE_TONE,
                 AIOperation.IMPROVE, AIOperation.REGENERATE_TITLE, AIOperation.REGENERATE_FRAGMENT,
                 AIOperation.GENERATE_CTA, AIOperation.REMOVE_CLICHES, AIOperation.GENERATE_IMAGE_PROMPT]


class Named(BaseModel):
    key: str
    label: str
    cost_rub: Decimal
    requests: int


class DayCost(BaseModel):
    day: date
    cost_rub: Decimal


class TopContent(BaseModel):
    content_id: uuid.UUID
    title: str
    status: str
    cost_rub: Decimal
    requests: int


class CostDashboardResponse(BaseModel):
    today_rub: Decimal
    week_rub: Decimal
    month_rub: Decimal
    daily_budget_rub: Decimal
    month_budget_rub: Decimal
    warning_pct: int
    forecast_month_end_rub: Decimal
    input_tokens_month: int
    output_tokens_month: int
    breakdown: list[Named]
    by_channel_set: list[Named]
    by_category: list[Named]
    by_provider: list[Named]
    daily: list[DayCost]
    top_content: list[TopContent]


def _d(v) -> Decimal:
    return Decimal(v or 0).quantize(Decimal("0.0001"))


@router.get("/costs", response_model=CostDashboardResponse)
async def cost_dashboard(workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member),
                         db: AsyncSession = Depends(get_db)):
    service = CostService(db)
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    budget = await service.budget_config(workspace_id)
    in_month = and_(AIRequest.workspace_id == workspace_id, AIRequest.created_at >= month_start)

    tokens = (await db.execute(select(func.coalesce(func.sum(AIRequest.prompt_tokens), 0),
                                      func.coalesce(func.sum(AIRequest.completion_tokens), 0)).where(in_month))).one()

    # Breakdown by kind of spend (month). AIRequest has the full picture incl.
    # failed/retried attempts; CostEvent holds only successful spend.
    rejected = [ContentStatus.REJECTED, ContentStatus.ARCHIVED, ContentStatus.FAILED]
    kind = case(
        (AIRequest.status != AIRequestStatus.SUCCESS, "failed"),
        (ContentItem.status.in_(rejected), "rejected"),
        (AIRequest.operation == AIOperation.GENERATE_IMAGE, "images"),
        (AIRequest.operation.in_(TRANSFORM_OPS), "transforms"),
        else_="generation",
    )
    labels = {"generation": "Generation", "transforms": "Edits & transforms", "images": "Images",
              "rejected": "Rejected / discarded posts", "failed": "Failed & retried AI calls"}
    rows = (await db.execute(
        select(kind.label("k"), func.coalesce(func.sum(AIRequest.total_cost_rub), 0), func.count())
        .outerjoin(ContentItem, ContentItem.id == AIRequest.content_item_id).where(in_month).group_by("k")
    )).all()
    found = {k: (c, n) for k, c, n in rows}
    breakdown = [Named(key=k, label=labels[k], cost_rub=_d(found.get(k, (0, 0))[0]), requests=found.get(k, (0, 0))[1])
                 for k in labels]

    async def grouped(col, label_map=None) -> list[Named]:
        rs = (await db.execute(
            select(col, func.coalesce(func.sum(AIRequest.total_cost_rub), 0), func.count())
            .outerjoin(ContentItem, ContentItem.id == AIRequest.content_item_id)
            .where(in_month).group_by(col).order_by(func.sum(AIRequest.total_cost_rub).desc()).limit(10)
        )).all()
        out = []
        for key, cost, n in rs:
            label = (label_map or {}).get(key) if label_map else None
            out.append(Named(key=str(key) if key else "none", label=label or (str(key) if key else "—"),
                             cost_rub=_d(cost), requests=n))
        return out

    set_names = dict((await db.execute(select(ChannelSet.id, ChannelSet.name)
                                       .where(ChannelSet.workspace_id == workspace_id))).all())
    by_set = await grouped(ContentItem.channel_set_id, set_names)
    for row in by_set:
        if row.key == "none":
            row.label = "No target"
    by_category = await grouped(ContentItem.category)
    by_provider = await grouped(AIRequest.provider)

    since = (now - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
    day_col = func.date(AIRequest.created_at)
    per_day = dict((await db.execute(
        select(day_col, func.coalesce(func.sum(AIRequest.total_cost_rub), 0))
        .where(AIRequest.workspace_id == workspace_id, AIRequest.created_at >= since).group_by(day_col)
    )).all())
    per_day = {(d if isinstance(d, date) else date.fromisoformat(str(d))): v for d, v in per_day.items()}
    daily = [DayCost(day=(since + timedelta(days=i)).date(), cost_rub=_d(per_day.get((since + timedelta(days=i)).date(), 0)))
             for i in range(30)]

    top = (await db.execute(
        select(ContentItem.id, ContentItem.title, ContentItem.topic, ContentItem.status,
               func.sum(AIRequest.total_cost_rub), func.count())
        .join(AIRequest, AIRequest.content_item_id == ContentItem.id)
        .where(ContentItem.workspace_id == workspace_id, AIRequest.created_at >= month_start)
        .group_by(ContentItem.id, ContentItem.title, ContentItem.topic, ContentItem.status)
        .order_by(func.sum(AIRequest.total_cost_rub).desc()).limit(10)
    )).all()

    return CostDashboardResponse(
        today_rub=_d(await service.today_spend(workspace_id)),
        week_rub=_d(await service.spend_since(workspace_id, now - timedelta(days=7))),
        month_rub=_d(await service.month_spend(workspace_id)),
        daily_budget_rub=_d(budget.daily_budget_rub), month_budget_rub=_d(budget.monthly_budget_rub),
        warning_pct=budget.budget_warning_pct or 80,
        forecast_month_end_rub=await service.forecast_month_end(workspace_id),
        input_tokens_month=int(tokens[0]), output_tokens_month=int(tokens[1]),
        breakdown=breakdown, by_channel_set=by_set, by_category=by_category, by_provider=by_provider, daily=daily,
        top_content=[TopContent(content_id=i, title=t or tp or "Untitled", status=s.value, cost_rub=_d(c), requests=n)
                     for i, t, tp, s, c, n in top],
    )


class PostBrief(BaseModel):
    content_id: uuid.UUID
    title: str
    status: str
    at: datetime | None
    channel_set_name: str | None
    targets: int
    published: int
    failed: int
    views: int = 0


class FailedPublication(BaseModel):
    content_id: uuid.UUID
    title: str
    channel_title: str
    error: str | None
    at: datetime


class DayViews(BaseModel):
    day: date
    views: int


class DashboardResponse(BaseModel):
    channels: int
    channels_healthy: int
    accounts: int
    accounts_connected: int
    posts_today: int
    scheduled: int
    pending_approval: int
    failed_publications_7d: int
    failed_jobs_7d: int
    next_scheduled: list[PostBrief]
    recent_published: list[PostBrief]
    recent_failed: list[FailedPublication]
    telegram_accounts: list[dict]
    ai_provider: dict
    system: dict
    views_7d: list[DayViews]
    top_posts: list[PostBrief]
    has_metrics: bool


async def _briefs(db: AsyncSession, items: list[ContentItem], at_attr: str) -> list[PostBrief]:
    from app.api.v1.content import _delivery_stats

    stats = await _delivery_stats(db, [i.id for i in items])
    names = dict((await db.execute(select(ChannelSet.id, ChannelSet.name)
                                   .where(ChannelSet.id.in_({i.channel_set_id for i in items if i.channel_set_id})))).all()) \
        if items else {}
    return [PostBrief(content_id=i.id, title=i.title or i.topic or "Untitled", status=i.status.value,
                      at=getattr(i, at_attr), channel_set_name=names.get(i.channel_set_id), targets=stats[i.id]["targets"],
                      published=stats[i.id]["published"], failed=stats[i.id]["failed"], views=stats[i.id]["views"])
            for i in items]


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member),
                    db: AsyncSession = Depends(get_db)):
    now = datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)
    count = lambda stmt: db.scalar(select(func.count()).select_from(stmt.subquery()))

    channels = await count(select(TelegramChannel.id).where(TelegramChannel.workspace_id == workspace_id))
    healthy = await count(select(TelegramChannel.id).where(TelegramChannel.workspace_id == workspace_id,
                                                           TelegramChannel.can_post.is_(True)))
    accounts = (await db.execute(select(TelegramAccount).where(TelegramAccount.workspace_id == workspace_id))).scalars().all()
    live = ContentItem.deleted_at.is_(None)
    posts_today = await count(select(ContentItem.id).where(ContentItem.workspace_id == workspace_id, live,
                                                           ContentItem.published_at >= today))
    scheduled = await count(select(ContentItem.id).where(ContentItem.workspace_id == workspace_id, live,
                                                         ContentItem.status == ContentStatus.SCHEDULED))
    pending = await count(select(ContentItem.id).where(ContentItem.workspace_id == workspace_id, live,
                                                       ContentItem.status == ContentStatus.PENDING_APPROVAL))
    failed_pubs = await count(
        select(Publication.id).join(DistributionBatch, Publication.batch_id == DistributionBatch.id)
        .where(DistributionBatch.workspace_id == workspace_id, Publication.status == PublicationStatus.FAILED,
               Publication.updated_at >= week_ago))
    failed_jobs = await count(select(Job.id).where(Job.workspace_id == workspace_id, Job.status == JobStatus.FAILED,
                                                   Job.created_at >= week_ago))

    next_items = (await db.execute(select(ContentItem).where(
        ContentItem.workspace_id == workspace_id, live, ContentItem.status == ContentStatus.SCHEDULED)
        .order_by(ContentItem.scheduled_at).limit(5))).scalars().all()
    recent_items = (await db.execute(select(ContentItem).where(
        ContentItem.workspace_id == workspace_id, live,
        ContentItem.status.in_([ContentStatus.PUBLISHED, ContentStatus.PARTIALLY_PUBLISHED]))
        .order_by(ContentItem.published_at.desc()).limit(5))).scalars().all()
    failed_rows = (await db.execute(
        select(Publication, ContentItem, TelegramChannel)
        .join(DistributionBatch, Publication.batch_id == DistributionBatch.id)
        .join(ContentItem, DistributionBatch.content_item_id == ContentItem.id)
        .join(TelegramChannel, Publication.channel_id == TelegramChannel.id)
        .where(DistributionBatch.workspace_id == workspace_id, Publication.status == PublicationStatus.FAILED)
        .order_by(Publication.updated_at.desc()).limit(5))).all()

    # views per day (last 7 days) from the latest snapshot of each publication, bucketed by publish day
    latest = (select(PostMetricSnapshot.publication_id, func.max(PostMetricSnapshot.captured_at).label("at"))
              .group_by(PostMetricSnapshot.publication_id).subquery())
    view_rows = (await db.execute(
        select(func.date(Publication.published_at), func.sum(PostMetricSnapshot.views))
        .join(DistributionBatch, Publication.batch_id == DistributionBatch.id)
        .join(latest, latest.c.publication_id == Publication.id)
        .join(PostMetricSnapshot, and_(PostMetricSnapshot.publication_id == Publication.id,
                                       PostMetricSnapshot.captured_at == latest.c.at))
        .where(DistributionBatch.workspace_id == workspace_id, Publication.published_at >= today - timedelta(days=6))
        .group_by(func.date(Publication.published_at)))).all()
    views_by_day = {(d if isinstance(d, date) else date.fromisoformat(str(d))): int(v or 0) for d, v in view_rows}
    views_7d = [DayViews(day=(today - timedelta(days=6 - i)).date(),
                         views=views_by_day.get((today - timedelta(days=6 - i)).date(), 0)) for i in range(7)]

    recent_briefs = await _briefs(db, list(recent_items), "published_at")
    top_candidates = (await db.execute(select(ContentItem).where(
        ContentItem.workspace_id == workspace_id, live, ContentItem.published_at >= now - timedelta(days=30))
        .order_by(ContentItem.published_at.desc()).limit(50))).scalars().all()
    top = sorted(await _briefs(db, list(top_candidates), "published_at"), key=lambda b: -b.views)[:5]
    top = [b for b in top if b.views > 0]

    image = get_image_provider()
    ready = await readiness()
    from app.core.config import get_settings

    return DashboardResponse(
        channels=channels or 0, channels_healthy=healthy or 0, accounts=len(accounts),
        accounts_connected=sum(1 for a in accounts if a.status == TelegramAccountStatus.CONNECTED),
        posts_today=posts_today or 0, scheduled=scheduled or 0, pending_approval=pending or 0,
        failed_publications_7d=failed_pubs or 0, failed_jobs_7d=failed_jobs or 0,
        next_scheduled=await _briefs(db, list(next_items), "scheduled_at"),
        recent_published=recent_briefs,
        recent_failed=[FailedPublication(content_id=c.id, title=c.title or "Untitled", channel_title=ch.title,
                                         error=p.error_message, at=p.updated_at) for p, c, ch in failed_rows],
        telegram_accounts=[{"id": str(a.id), "phone": a.phone_masked, "status": a.status.value,
                            "flood_wait_until": a.flood_wait_until.isoformat() if a.flood_wait_until else None,
                            "last_heartbeat_at": a.last_heartbeat_at.isoformat() if a.last_heartbeat_at else None}
                           for a in accounts],
        ai_provider={"text": get_text_provider().name, "text_fake": get_settings().use_fake_ai_provider,
                     "image": image.name, "image_status": (await image.status()).value},
        system=ready, views_7d=views_7d, top_posts=top, has_metrics=bool(views_by_day),
    )


@router.get("/content/{content_id}")
async def content_item_analytics(
    workspace_id: uuid.UUID, content_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    item = await db.get(ContentItem, content_id)
    if not item or item.workspace_id != workspace_id:
        raise ApiError(404, "CONTENT_NOT_FOUND", "Content item not found")
    totals = await AnalyticsService(db).content_item_totals(content_id)
    titles = dict((await db.execute(select(TelegramChannel.id, TelegramChannel.title)
                                    .where(TelegramChannel.workspace_id == workspace_id))).all())
    for row in totals["per_channel"]:
        row["channel_title"] = titles.get(uuid.UUID(row["channel_id"]), "")
    return totals


@router.get("/performance")
async def performance(workspace_id: uuid.UUID, days: int = Query(default=30, ge=1, le=90),
                      member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db)):
    """Per-channel totals over the period, from the latest snapshot of each publication."""
    since = datetime.now(UTC) - timedelta(days=days)
    latest = (select(PostMetricSnapshot.publication_id, func.max(PostMetricSnapshot.captured_at).label("at"))
              .group_by(PostMetricSnapshot.publication_id).subquery())
    rows = (await db.execute(
        select(TelegramChannel.id, TelegramChannel.title, func.count(Publication.id),
               func.coalesce(func.sum(PostMetricSnapshot.views), 0), func.coalesce(func.sum(PostMetricSnapshot.forwards), 0),
               func.coalesce(func.sum(PostMetricSnapshot.reactions), 0))
        .join(Publication, Publication.channel_id == TelegramChannel.id)
        .join(latest, latest.c.publication_id == Publication.id)
        .join(PostMetricSnapshot, and_(PostMetricSnapshot.publication_id == Publication.id,
                                       PostMetricSnapshot.captured_at == latest.c.at))
        .where(TelegramChannel.workspace_id == workspace_id, Publication.published_at >= since)
        .group_by(TelegramChannel.id, TelegramChannel.title)
        .order_by(func.sum(PostMetricSnapshot.views).desc())
    )).all()
    return [{"channel_id": str(i), "channel_title": t, "posts": n, "views": int(v), "forwards": int(f),
             "reactions": int(r)} for i, t, n, v, f, r in rows]
