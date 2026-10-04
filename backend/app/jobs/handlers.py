"""Job handlers, one per JobType. Each runs inside a session opened by
app.services.jobs.service.run_job and reports its outcome by returning
(success), raising RetryLater (try again later) or JobFailed (terminal).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobType, PublicationStatus
from app.models.ops import Job
from app.services.jobs.service import Emit, JobFailed, RetryLater, backoff_for, register_handler


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


@register_handler(JobType.TELEGRAM_PUBLISH)
@register_handler(JobType.TELEGRAM_RETRY)
async def publish_handler(session: AsyncSession, job: Job, payload: dict[str, Any], emit: Emit) -> dict[str, Any]:
    from app.models.telegram import TelegramAccount, TelegramChannel
    from app.services.media.storage import MediaStorage
    from app.services.notifications.service import NotificationService
    from app.services.publishing.publishing_service import DELIVERY_UNKNOWN, PublishingService

    publication_id = uuid.UUID(payload["publication_id"])
    emit("publication.started", {"publication_id": str(publication_id)})
    publication = await PublishingService(session, MediaStorage()).publish(publication_id)
    base = {
        "publication_id": str(publication.id),
        "batch_id": str(publication.batch_id),
        "channel_id": str(publication.channel_id),
        "status": publication.status.value,
    }

    if publication.status == PublicationStatus.SUCCESS:
        emit("publication.published", {**base, "telegram_message_id": publication.telegram_message_id})
        await NotificationService(session).on_batch_progress(publication, emit)
        return {"telegram_message_id": publication.telegram_message_id}

    if publication.status == PublicationStatus.FAILED:
        emit("publication.failed", {**base, "error": publication.error_message})
        await NotificationService(session).on_publication_failed(publication, emit)
        raise JobFailed(publication.error_code or "PUBLISH_FAILED", publication.error_message or "Publish failed")

    if publication.status == PublicationStatus.SENDING and publication.error_code == DELIVERY_UNKNOWN:
        emit("publication.failed", {**base, "error": publication.error_message})
        raise JobFailed(DELIVERY_UNKNOWN, publication.error_message or "Delivery state unknown")

    if publication.status == PublicationStatus.PENDING:
        channel = await session.get(TelegramChannel, publication.channel_id)
        account = await session.get(TelegramAccount, channel.account_id)
        if account.flood_wait_until and _aware(account.flood_wait_until) > datetime.now(UTC):
            retry_at = _aware(account.flood_wait_until)
            code, message = "FLOOD_WAIT", f"FloodWait: retry scheduled in {int((retry_at - datetime.now(UTC)).total_seconds())} seconds."
            emit("telegram.account.health_changed", {"account_id": str(account.id), "status": account.status.value,
                                                     "flood_wait_until": retry_at.isoformat()})
            await NotificationService(session).on_flood_wait(account, retry_at, emit)
        else:
            retry_at = datetime.now(UTC) + backoff_for(max(1, publication.attempt))
            code, message = publication.error_code or "NETWORK", publication.error_message or "Temporary error"
        emit("publication.retry_scheduled", {**base, "retry_at": retry_at.isoformat(), "reason": code})
        raise RetryLater(retry_at, code, message)

    if publication.status in (PublicationStatus.SENDING, PublicationStatus.CLAIMED):
        updated = _aware(publication.updated_at)
        if updated and datetime.now(UTC) - updated < timedelta(minutes=5):
            # Probably another worker is sending right now; look again shortly.
            raise RetryLater(datetime.now(UTC) + timedelta(minutes=2), "IN_FLIGHT", "Publication is being sent")
        # Left mid-send by a crashed worker: we can't know if Telegram got it.
        publication.error_code = DELIVERY_UNKNOWN
        publication.error_message = (
            "Delivery state unknown (the worker stopped mid-send). Check the channel, then mark this "
            "publication as published or failed."
        )
        emit("publication.failed", {**base, "error": publication.error_message})
        raise JobFailed(DELIVERY_UNKNOWN, publication.error_message)

    # Already SUCCESS before this delivery: nothing to do.
    return {"note": f"publication already {publication.status.value}"}


@register_handler(JobType.TELEGRAM_REFRESH_CHANNELS)
async def refresh_channels_handler(session: AsyncSession, job: Job, payload: dict[str, Any], emit: Emit) -> dict[str, Any]:
    from app.services.audit.service import AuditService
    from app.services.telegram.account_service import TelegramAccountService
    from app.services.telegram.base import TelegramOperationError

    account_id = uuid.UUID(payload["account_id"])
    try:
        channels = await TelegramAccountService(session).refresh_channels(
            workspace_id=job.workspace_id, account_id=account_id
        )
    except ValueError as exc:
        raise JobFailed("ACCOUNT_NOT_FOUND", str(exc)) from exc
    except TelegramOperationError as exc:
        await session.commit()  # keep AUTH_REQUIRED status on the account
        emit("telegram.account.health_changed", {"account_id": str(account_id)})
        raise JobFailed(exc.kind.value, str(exc)) from exc
    await AuditService(session).record(
        workspace_id=job.workspace_id, actor_user_id=job.created_by_user_id, action="telegram.channels_imported",
        entity_type="telegram_account", entity_id=account_id, metadata={"channels": len(channels)},
    )
    emit("telegram.account.health_changed", {"account_id": str(account_id), "channels": len(channels)})
    return {"channels": len(channels)}


@register_handler(JobType.TELEGRAM_REFRESH_METRICS)
async def refresh_metrics_handler(session: AsyncSession, job: Job, payload: dict[str, Any], emit: Emit) -> dict[str, Any]:
    from app.models.distribution import DistributionBatch, Publication
    from app.services.analytics.service import AnalyticsService
    from app.services.jobs.service import set_progress

    since = datetime.now(UTC) - timedelta(days=int(payload.get("days", 7)))
    result = await session.execute(
        select(Publication)
        .join(DistributionBatch, Publication.batch_id == DistributionBatch.id)
        .where(
            DistributionBatch.workspace_id == job.workspace_id,
            Publication.status == PublicationStatus.SUCCESS,
            Publication.published_at >= since,
        )
    )
    publications = list(result.scalars().all())
    service = AnalyticsService(session)
    collected = failed = 0
    for i, pub in enumerate(publications, start=1):
        try:
            if await service.collect_metrics_for_publication(pub):
                collected += 1
        except Exception:  # noqa: BLE001 — one unreachable channel must not stop the rest
            failed += 1
        if i % 10 == 0:
            await set_progress(session, job, int(i * 100 / len(publications)))
    return {"collected": collected, "failed": failed}


@register_handler(JobType.SOURCE_FETCH)
async def source_fetch_handler(session: AsyncSession, job: Job, payload: dict[str, Any], emit: Emit) -> dict[str, Any]:
    from app.models.sources import Source
    from app.services.content.source_service import SourceFetchError, SourceService

    source = await session.get(Source, uuid.UUID(payload["source_id"]))
    if source is None or source.workspace_id != job.workspace_id:
        raise JobFailed("SOURCE_NOT_FOUND", "Source no longer exists")
    try:
        new_items = await SourceService(session).fetch(source)
    except SourceFetchError as exc:
        await session.commit()  # persist last_error / last_fetched_at
        raise JobFailed("SOURCE_FETCH_FAILED", str(exc)) from exc
    return {"new_items": new_items}


@register_handler(JobType.AUTOPILOT_PLAN)
async def autopilot_handler(session: AsyncSession, job: Job, payload: dict[str, Any], emit: Emit) -> dict[str, Any]:
    from app.models.scheduling import AutopilotConfig
    from app.services.ai.factory import get_image_provider, get_text_provider
    from app.services.ai.service import AIService
    from app.services.content.service import ContentService
    from app.services.scheduling.autopilot_service import AutopilotService

    result = await session.execute(select(AutopilotConfig).where(AutopilotConfig.workspace_id == job.workspace_id))
    config = result.scalar_one_or_none()
    if config is None:
        return {"created": 0, "note": "no autopilot config"}
    ai_service = AIService(session, get_text_provider(), get_image_provider())
    autopilot = AutopilotService(session, ContentService(session, ai_service))
    created = []
    for _ in range(config.posts_per_day):
        item = await autopilot.plan_one(workspace_id=job.workspace_id, config=config)
        if item is None:
            break
        created.append(str(item.id))
        emit("content.generated", {"content_id": str(item.id), "status": item.status.value})
    return {"created": len(created), "content_ids": created}


@register_handler(JobType.AI_GENERATE_POST)
async def generate_handler(session: AsyncSession, job: Job, payload: dict[str, Any], emit: Emit) -> dict[str, Any]:
    from app.services.content.generation import run_generation

    return await run_generation(session, job, payload, emit)


@register_handler(JobType.AI_REWRITE)
async def transform_handler(session: AsyncSession, job: Job, payload: dict[str, Any], emit: Emit) -> dict[str, Any]:
    from app.services.content.transforms import run_transform

    return await run_transform(session, job, payload, emit)
