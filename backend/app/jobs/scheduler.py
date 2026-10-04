"""Standalone scheduler process. Polls for content whose scheduled_at is due,
enqueues TELEGRAM_PUBLISH for each still-PENDING publication in its batch, and
fires AUTOPILOT_PLAN once per workspace per day. Runs separately from the API
and worker processes (ARCHITECTURE.md §4).
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from sqlalchemy import or_, select

from app.core.logging import configure_logging
from app.db.session import AsyncSessionLocal
from app.jobs.queue import get_arq_pool
from app.models.content import ContentItem
from app.models.distribution import DistributionBatch, Publication
from app.models.enums import ContentStatus, PublicationStatus
from app.models.scheduling import AutopilotConfig
from app.models.telegram import TelegramAccount, TelegramChannel

log = structlog.get_logger(__name__)

POLL_INTERVAL_SECONDS = 15
_last_autopilot_run: dict[str, str] = {}


async def tick() -> None:
    pool = await get_arq_pool()
    now = datetime.now(UTC)

    async with AsyncSessionLocal() as session:
        due_result = await session.execute(
            select(ContentItem).where(
                ContentItem.status == ContentStatus.SCHEDULED, ContentItem.scheduled_at <= now
            )
        )
        due_items = due_result.scalars().all()

        for item in due_items:
            item.status = ContentStatus.PUBLISHING
        await session.commit()

        # Drive every still-PENDING publication of content that is publishing.
        # This covers first sends, FloodWait reschedules, network retries and
        # manual "retry failed" in one place. Accounts still inside a FloodWait
        # window are skipped. The ARQ job id includes the attempt number, so a
        # publication already queued for this attempt is not enqueued twice;
        # PublishingService's atomic claim is the second line of defense.
        # CLAIMED/SENDING rows left by a crashed worker are deliberately NOT
        # re-sent automatically: we cannot know whether Telegram received them.
        pending_result = await session.execute(
            select(Publication)
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
        for pub in pending_result.scalars().all():
            await pool.enqueue_job(
                "telegram_publish", str(pub.id), _job_id=f"publish:{pub.id}:{pub.attempt}"
            )

        configs_result = await session.execute(select(AutopilotConfig))
        for config in configs_result.scalars().all():
            key = f"{config.workspace_id}:{now.date().isoformat()}"
            if _last_autopilot_run.get(str(config.workspace_id)) != key and config.mode.value != "MANUAL":
                _last_autopilot_run[str(config.workspace_id)] = key
                await pool.enqueue_job("autopilot_plan", str(config.workspace_id))


async def main() -> None:
    configure_logging()
    log.info("scheduler_started", poll_interval=POLL_INTERVAL_SECONDS)
    while True:
        try:
            await tick()
        except Exception:
            log.exception("scheduler_tick_failed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
