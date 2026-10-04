"""Standalone scheduler process (`python -m app.jobs.scheduler`).

Every tick (under a Redis lock, so extra replicas are harmless):
1. misfire policy for posts whose time passed while the scheduler was down;
2. due SCHEDULED content -> PUBLISHING;
3. every PENDING publication of PUBLISHING content gets exactly one active
   publish Job (created, or re-queued when its retry time comes);
4. other RETRYING jobs whose time came are re-queued; stale QUEUED jobs are
   re-dispatched (lost Redis message); stale RUNNING jobs are recovered;
5. daily Autopilot, due source fetches, hourly metrics refresh — all recorded
   as Jobs, so no in-memory state survives or is needed across restarts.
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, or_, select

from app.core.lease import lease
from app.core.logging import configure_logging
from app.core.redis import get_redis
from app.db.session import session_scope
from app.models.content import ContentItem
from app.models.distribution import DistributionBatch, Publication
from app.models.enums import AutopilotMode, ContentStatus, JobStatus, JobType, PublicationStatus
from app.models.ops import Job
from app.models.scheduling import AutopilotConfig, Schedule, ScheduleRule
from app.models.settings import WorkspaceSettings
from app.models.sources import Source
from app.models.telegram import TelegramAccount, TelegramChannel
from app.services.jobs.service import JobService, backoff_for, dispatch
from app.services.scheduling.service import ScheduleService
from app.services.system.health import SCHEDULER_HEARTBEAT_KEY, beat

log = structlog.get_logger(__name__)

POLL_INTERVAL_SECONDS = 15
LOCK_KEY = "scheduler:lock"
STALE_QUEUED = timedelta(minutes=10)
STALE_RUNNING = timedelta(minutes=15)  # > ARQ job_timeout
METRICS_EVERY = timedelta(hours=1)
DEFAULT_MISFIRE_SPACING = timedelta(minutes=60)
MISFIRE_POLICIES = ("SKIP", "PUBLISH_IMMEDIATELY", "RESCHEDULE_NEXT_SLOT")


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def _policy_for(session, item: ContentItem, cache: dict) -> tuple[str, int]:
    if item.workspace_id not in cache:
        ws = (
            await session.execute(select(WorkspaceSettings).where(WorkspaceSettings.workspace_id == item.workspace_id))
        ).scalar_one_or_none()
        cache[item.workspace_id] = (ws.misfire_policy if ws else "RESCHEDULE_NEXT_SLOT",
                                    ws.misfire_grace_minutes if ws else 15)
    policy, grace = cache[item.workspace_id]
    if item.schedule_id:
        schedule = await session.get(Schedule, item.schedule_id)
        if schedule and schedule.misfire_policy:
            policy = schedule.misfire_policy
    return policy, grace


async def handle_misfires(session, now: datetime) -> list[tuple[ContentItem, str]]:
    """Posts overdue by more than the grace period are not all fired at once."""
    from app.services.audit.service import AuditService
    from app.services.notifications.service import NotificationService

    overdue = (
        await session.execute(
            select(ContentItem)
            .where(ContentItem.status == ContentStatus.SCHEDULED, ContentItem.scheduled_at < now - timedelta(minutes=1))
            .order_by(ContentItem.scheduled_at).with_for_update(skip_locked=True)
        )
    ).scalars().all()
    cache: dict = {}
    handled: list[tuple[ContentItem, str]] = []
    cursors: dict = {}  # per target: next free time for staggered rescheduling
    schedules = ScheduleService()
    for item in overdue:
        policy, grace = await _policy_for(session, item, cache)
        if _aware(item.scheduled_at) >= now - timedelta(minutes=grace):
            continue  # late but within grace: publish normally
        original = _aware(item.scheduled_at)
        if policy == "PUBLISH_IMMEDIATELY":
            continue  # promoted below like any due item
        if policy == "SKIP":
            item.status = ContentStatus.APPROVED
            item.scheduled_at = None
            outcome = "skipped"
        else:  # RESCHEDULE_NEXT_SLOT
            new_time = None
            target_key = item.channel_set_id or item.id
            if item.schedule_id:
                schedule = await session.get(Schedule, item.schedule_id)
                rules = (await session.execute(select(ScheduleRule).where(ScheduleRule.schedule_id == item.schedule_id))).scalars().all()
                occupied = await _occupied_times(session, item)
                occupied += cursors.get(target_key, [])
                if schedule:
                    new_time = schedules.next_free_slot(schedule, rules, after=now, occupied=occupied)
            if new_time is None:
                previous = max(cursors.get(target_key, [now]))
                new_time = max(now + timedelta(minutes=5), previous + DEFAULT_MISFIRE_SPACING) \
                    if target_key in cursors else now + timedelta(minutes=5)
            cursors.setdefault(target_key, []).append(new_time)
            item.scheduled_at = new_time
            outcome = f"rescheduled to {new_time.isoformat()}"
        await AuditService(session).record(
            workspace_id=item.workspace_id, actor_user_id=None, action="content.misfire_" + policy.lower(),
            entity_type="content", entity_id=item.id,
            metadata={"original_time": original.isoformat(), "outcome": outcome},
        )
        handled.append((item, outcome))
    by_ws: dict = {}
    for item, _ in handled:
        by_ws.setdefault(item.workspace_id, []).append(item)
    for workspace_id, items in by_ws.items():
        await NotificationService(session).notify(
            workspace_id=workspace_id, kind="schedule.misfired",
            message=f"{len(items)} scheduled post(s) were missed while the scheduler was offline and have been "
                    f"handled by the misfire policy. Review them in the calendar.",
            metadata={"content_ids": [str(i.id) for i in items]},
        )
    return handled


async def _occupied_times(session, item: ContentItem) -> list[datetime]:
    if not item.channel_set_id:
        return []
    rows = await session.execute(
        select(ContentItem.scheduled_at).where(
            ContentItem.channel_set_id == item.channel_set_id,
            ContentItem.status == ContentStatus.SCHEDULED,
            ContentItem.id != item.id,
            ContentItem.scheduled_at.is_not(None),
        )
    )
    return [_aware(r[0]) for r in rows.all()]


async def promote_due(session, now: datetime) -> int:
    due = (
        await session.execute(
            select(ContentItem).where(ContentItem.status == ContentStatus.SCHEDULED, ContentItem.scheduled_at <= now).with_for_update(skip_locked=True)
        )
    ).scalars().all()
    for item in due:
        item.status = ContentStatus.PUBLISHING
    return len(due)


async def drive_publications(session, now: datetime) -> list[Job]:
    pending = (
        await session.execute(
            select(Publication, DistributionBatch.workspace_id, TelegramChannel.title)
            .join(DistributionBatch, Publication.batch_id == DistributionBatch.id)
            .join(ContentItem, DistributionBatch.content_item_id == ContentItem.id)
            .join(TelegramChannel, Publication.channel_id == TelegramChannel.id)
            .join(TelegramAccount, TelegramChannel.account_id == TelegramAccount.id)
            .where(
                Publication.status == PublicationStatus.PENDING,
                ContentItem.status == ContentStatus.PUBLISHING,
                or_(TelegramAccount.flood_wait_until.is_(None), TelegramAccount.flood_wait_until <= now),
            )
        )
    ).all()
    service = JobService(session)
    to_dispatch: list[Job] = []
    for pub, workspace_id, channel_title in pending:
        job = await service.active_for_entity("publication", pub.id)
        if job is None:
            job = await service.create(
                workspace_id=workspace_id, job_type=JobType.TELEGRAM_PUBLISH,
                payload={"publication_id": str(pub.id)}, entity_type="publication", entity_id=pub.id,
                summary=f"Publish to {channel_title}", max_attempts=5,
            )
            to_dispatch.append(job)
        elif job.status == JobStatus.RETRYING and (_aware(job.next_retry_at) or now) <= now:
            job.status = JobStatus.QUEUED
            job.queued_at = now
            to_dispatch.append(job)
    return to_dispatch


async def requeue_and_recover(session, now: datetime) -> list[Job]:
    to_dispatch: list[Job] = []
    retrying = (
        await session.execute(
            # Publish jobs of PENDING publications were re-queued by drive_publications
            # (now QUEUED, so not matched here); this catches everything else,
            # e.g. a publish job whose publication is stuck mid-send.
            select(Job).where(Job.status == JobStatus.RETRYING, Job.next_retry_at <= now)
        )
    ).scalars().all()
    for job in retrying:
        job.status = JobStatus.QUEUED
        job.queued_at = now
        to_dispatch.append(job)

    stale_queued = (
        await session.execute(select(Job).where(Job.status == JobStatus.QUEUED, Job.queued_at < now - STALE_QUEUED))
    ).scalars().all()
    for job in stale_queued:
        job.queued_at = now  # re-dispatch; ARQ _job_id dedup prevents doubles if the message still exists
        to_dispatch.append(job)

    stale_running = (
        await session.execute(select(Job).where(Job.status == JobStatus.RUNNING, Job.started_at < now - STALE_RUNNING))
    ).scalars().all()
    for job in stale_running:
        # The worker died or timed out mid-job. Publishing stays safe: a publication
        # left SENDING is "delivery unknown" and the handler won't send it again.
        job.error_code = "WORKER_LOST"
        job.error_message = "The worker stopped while running this job."
        if job.attempt < job.max_attempts:
            job.status = JobStatus.RETRYING
            job.next_retry_at = now + backoff_for(job.attempt)
        else:
            job.status = JobStatus.FAILED
            job.finished_at = now
    return to_dispatch


async def periodic_jobs(session, now: datetime) -> list[Job]:
    service = JobService(session)
    created: list[Job] = []
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    configs = (
        await session.execute(select(AutopilotConfig).where(AutopilotConfig.mode != AutopilotMode.MANUAL))
    ).scalars().all()
    for config in configs:
        already = await session.scalar(
            select(func.count()).select_from(Job).where(
                Job.workspace_id == config.workspace_id, Job.job_type == JobType.AUTOPILOT_PLAN,
                Job.created_at >= day_start,
            )
        )
        if not already:
            created.append(await service.create(
                workspace_id=config.workspace_id, job_type=JobType.AUTOPILOT_PLAN,
                payload={}, entity_type="workspace", entity_id=config.workspace_id,
                summary=f"Autopilot plan for {now.date().isoformat()}", max_attempts=1,
            ))

    sources = (await session.execute(select(Source).where(Source.is_active.is_(True)))).scalars().all()
    for source in sources:
        interval = timedelta(minutes=int(json.loads(source.config_json or "{}").get("fetch_interval_minutes", 60)))
        if source.kind not in ("rss", "url", "telegram"):
            continue
        if source.last_fetched_at and _aware(source.last_fetched_at) + interval > now:
            continue
        if await service.active_for_entity("source", source.id):
            continue
        created.append(await service.create(
            workspace_id=source.workspace_id, job_type=JobType.SOURCE_FETCH,
            payload={"source_id": str(source.id)}, entity_type="source", entity_id=source.id,
            summary=f"Fetch {source.name}", max_attempts=3,
        ))

    workspaces = (
        await session.execute(
            select(DistributionBatch.workspace_id)
            .join(Publication, Publication.batch_id == DistributionBatch.id)
            .where(Publication.status == PublicationStatus.SUCCESS, Publication.published_at >= now - timedelta(days=7))
            .distinct()
        )
    ).scalars().all()
    for workspace_id in workspaces:
        recent = await session.scalar(
            select(func.count()).select_from(Job).where(
                Job.workspace_id == workspace_id, Job.job_type == JobType.TELEGRAM_REFRESH_METRICS,
                Job.created_at >= now - METRICS_EVERY,
            )
        )
        if not recent:
            created.append(await service.create(
                workspace_id=workspace_id, job_type=JobType.TELEGRAM_REFRESH_METRICS,
                payload={"days": 7}, entity_type="workspace", entity_id=workspace_id,
                summary="Refresh post metrics (last 7 days)", max_attempts=2,
            ))
    return created


async def tick(now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    redis = get_redis()
    async with lease(redis, LOCK_KEY) as acquired:
        if not acquired:
            return {"skipped": 1}
        await beat(SCHEDULER_HEARTBEAT_KEY)
        async with session_scope() as session:
            misfired = await handle_misfires(session, now)
            promoted = await promote_due(session, now)
            await session.commit()

        async with session_scope() as session:
            jobs = await drive_publications(session, now)
            jobs += await requeue_and_recover(session, now)
            jobs += await periodic_jobs(session, now)
            await session.commit()
        for job in jobs:
            await dispatch(job)
        return {"misfired": len(misfired), "promoted": promoted, "dispatched": len(jobs)}


async def main() -> None:
    configure_logging()
    log.info("scheduler_started", poll_interval=POLL_INTERVAL_SECONDS)
    while True:
        try:
            result = await tick()
            if any(result.get(k) for k in ("misfired", "promoted", "dispatched")):
                log.info("scheduler_tick", **result)
        except Exception:
            log.exception("scheduler_tick_failed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
