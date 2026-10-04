"""ARQ task functions. Each wraps one unit of work from app/models/enums.py's
JobType and records a Job/JobAttempt row so the Jobs UI has something to show
even though ARQ itself also tracks retries internally.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.enums import JobStatus, JobType
from app.models.ops import Job, JobAttempt
from app.services.analytics.service import AnalyticsService
from app.services.media.storage import MediaStorage
from app.services.publishing.publishing_service import PublishingService

log = structlog.get_logger(__name__)


async def _record_job(workspace_id: uuid.UUID, job_type: JobType, payload: dict) -> Job:
    async with AsyncSessionLocal() as session:
        job = Job(workspace_id=workspace_id, job_type=job_type, payload_json=_dumps(payload))
        session.add(job)
        await session.commit()
        return job


async def _mark_running(job_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if job:
            job.status = JobStatus.RUNNING
            job.attempt += 1
            job.started_at = datetime.now(UTC)
            await session.commit()


async def _mark_result(job_id: uuid.UUID, status: JobStatus, error: str | None = None) -> None:
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if job:
            job.status = status
            job.error = error
            job.finished_at = datetime.now(UTC)
            session.add(
                JobAttempt(
                    job_id=job.id, attempt_number=job.attempt, status=status, error=error,
                    started_at=job.started_at, finished_at=job.finished_at,
                )
            )
            await session.commit()


async def telegram_publish(ctx, publication_id: str) -> None:
    async with AsyncSessionLocal() as session:
        storage = MediaStorage()
        service = PublishingService(session, storage)
        try:
            await service.publish(uuid.UUID(publication_id))
            await session.commit()
        except Exception:
            await session.rollback()
            log.exception("telegram_publish_failed", publication_id=publication_id)
            raise


async def telegram_refresh_metrics(ctx, publication_id: str) -> None:
    from app.models.distribution import Publication

    async with AsyncSessionLocal() as session:
        pub = await session.get(Publication, uuid.UUID(publication_id))
        if not pub:
            return
        service = AnalyticsService(session)
        await service.collect_metrics_for_publication(pub)
        await session.commit()


async def source_fetch(ctx, source_id: str) -> None:
    from app.models.sources import Source
    from app.services.content.source_service import SourceService

    async with AsyncSessionLocal() as session:
        source = await session.get(Source, uuid.UUID(source_id))
        if not source:
            return
        service = SourceService(session)
        if source.kind == "rss":
            await service.fetch_rss(source)
        await session.commit()


async def autopilot_plan(ctx, workspace_id: str) -> None:
    from app.models.scheduling import AutopilotConfig
    from app.services.ai.factory import get_image_provider, get_text_provider
    from app.services.ai.service import AIService
    from app.services.content.service import ContentService
    from app.services.scheduling.autopilot_service import AutopilotService

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AutopilotConfig).where(AutopilotConfig.workspace_id == uuid.UUID(workspace_id))
        )
        config = result.scalar_one_or_none()
        if not config:
            return
        ai_service = AIService(session, get_text_provider(), get_image_provider())
        content_service = ContentService(session, ai_service)
        autopilot = AutopilotService(session, content_service)
        for _ in range(config.posts_per_day):
            await autopilot.plan_one(workspace_id=uuid.UUID(workspace_id), config=config)
        await session.commit()


def _dumps(data: dict) -> str:
    import json

    return json.dumps(data, ensure_ascii=False, default=str)
