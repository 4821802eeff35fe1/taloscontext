"""Persistent background jobs.

Every background operation is a `Job` row first and an ARQ message second.
The row is the source of truth for the Jobs UI, retries and dedup; the ARQ
message only carries the job id. If Redis loses the message, the scheduler
notices a stale QUEUED row and re-dispatches it (ARQ `_job_id` dedup plus
handler-level idempotency make that safe).

Handlers live in app/jobs/handlers.py and are registered per JobType.
"""
from __future__ import annotations

import json
import os
import socket
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import session_scope
from app.models.enums import JobStatus, JobType
from app.models.ops import Job, JobAttempt
from app.services.realtime.events import publish_event

log = structlog.get_logger(__name__)

ACTIVE_STATUSES = {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYING}
TERMINAL_STATUSES = {JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED}

# Job types a user may re-run from the UI after FAILED. Publishing is handled
# separately: it's only retryable when the publication is known not to have
# been delivered (status FAILED), see JobService.retry.
USER_RETRYABLE = {
    JobType.AI_GENERATE_POST,
    JobType.AI_REWRITE,
    JobType.TELEGRAM_PUBLISH,
    JobType.TELEGRAM_RETRY,
    JobType.TELEGRAM_REFRESH_CHANNELS,
    JobType.TELEGRAM_REFRESH_METRICS,
    JobType.SOURCE_FETCH,
    JobType.AUTOPILOT_PLAN,
}

Emit = Callable[[str, dict[str, Any]], None]
# handler(session, job, payload, emit) -> result metadata. `emit` queues a
# realtime event that is published only after the handler's work commits.
Handler = Callable[[AsyncSession, Job, dict[str, Any], Emit], Awaitable[dict[str, Any] | None]]
_HANDLERS: dict[JobType, Handler] = {}


def register_handler(job_type: JobType):
    def decorator(fn: Handler) -> Handler:
        _HANDLERS[job_type] = fn
        return fn

    return decorator


class RetryLater(Exception):
    """Handler outcome: not done, try again at `at` (FloodWait, transient network)."""

    def __init__(self, at: datetime, code: str, message: str):
        super().__init__(message)
        self.at = at
        self.code = code
        self.message = message


class JobFailed(Exception):
    """Handler outcome: terminal failure that must not be retried automatically."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class JobNotRetryableError(Exception):
    pass


def backoff_for(attempt: int) -> timedelta:
    return timedelta(seconds=min(30 * (2 ** max(0, attempt - 1)), 30 * 60))


def _job_event_payload(job: Job) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "job_type": job.job_type.value,
        "status": job.status.value,
        "progress": job.progress,
        "entity_type": job.entity_type,
        "entity_id": job.entity_id,
        "attempt": job.attempt,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "next_retry_at": job.next_retry_at.isoformat() if job.next_retry_at else None,
    }


class JobService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        workspace_id: uuid.UUID,
        job_type: JobType,
        payload: dict[str, Any] | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | str | None = None,
        summary: str = "",
        max_attempts: int = 5,
        created_by_user_id: uuid.UUID | None = None,
    ) -> Job:
        job = Job(
            workspace_id=workspace_id,
            job_type=job_type,
            status=JobStatus.QUEUED,
            payload_json=json.dumps(payload or {}, default=str),
            payload_summary=summary[:500],
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            max_attempts=max_attempts,
            queued_at=datetime.now(UTC),
            created_by_user_id=created_by_user_id,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def active_for_entity(self, entity_type: str, entity_id: uuid.UUID | str) -> Job | None:
        result = await self.session.execute(
            select(Job)
            .where(
                Job.entity_type == entity_type,
                Job.entity_id == str(entity_id),
                Job.status.in_(ACTIVE_STATUSES),
            )
            .order_by(Job.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def cancel(self, job: Job) -> Job:
        if job.status not in (JobStatus.QUEUED, JobStatus.RETRYING):
            raise JobNotRetryableError(f"Only queued jobs can be cancelled (job is {job.status.value})")
        if job.job_type in (JobType.TELEGRAM_PUBLISH, JobType.TELEGRAM_RETRY) and job.entity_id:
            # Otherwise the scheduler would just queue the still-pending publication again.
            from app.models.distribution import DistributionBatch, Publication
            from app.models.enums import PublicationStatus
            from app.services.publishing.distribution_service import DistributionService

            pub = await self.session.get(Publication, uuid.UUID(job.entity_id))
            if pub is not None and pub.status == PublicationStatus.PENDING:
                pub.status = PublicationStatus.FAILED
                pub.error_code = "CANCELLED"
                pub.error_message = "Publishing was cancelled; it can be retried."
                await self.session.flush()
                batch = await self.session.get(DistributionBatch, pub.batch_id)
                if batch:
                    await DistributionService(self.session).recompute_batch_status(batch)
        job.status = JobStatus.CANCELLED
        job.finished_at = datetime.now(UTC)
        await self.session.flush()
        return job

    async def retry(self, job: Job) -> Job:
        """Re-queues a FAILED job when doing so cannot break idempotency."""
        if job.status != JobStatus.FAILED:
            raise JobNotRetryableError("Only failed jobs can be retried")
        if job.job_type not in USER_RETRYABLE:
            raise JobNotRetryableError(f"{job.job_type.value} jobs cannot be retried")
        if job.job_type in (JobType.TELEGRAM_PUBLISH, JobType.TELEGRAM_RETRY):
            from app.models.distribution import Publication
            from app.models.enums import PublicationStatus

            pub = await self.session.get(Publication, uuid.UUID(job.entity_id)) if job.entity_id else None
            if pub is None:
                raise JobNotRetryableError("Publication no longer exists")
            if pub.status != PublicationStatus.FAILED:
                # SUCCESS: already delivered. CLAIMED/SENDING: delivery state unknown —
                # re-sending could post twice, so this needs a human decision.
                raise JobNotRetryableError(
                    f"Publication is {pub.status.value}; retry is only allowed for failed publications"
                )
            pub.status = PublicationStatus.PENDING
        job.status = JobStatus.QUEUED
        job.attempt = 0
        job.error_code = None
        job.error_message = None
        job.next_retry_at = None
        job.finished_at = None
        job.queued_at = datetime.now(UTC)
        await self.session.flush()
        return job


async def dispatch(job: Job) -> None:
    """Hands a committed QUEUED job to the executor.

    Must be called after the creating transaction commits, otherwise the
    worker could look the row up before it exists.
    """
    await publish_event(job.workspace_id, "job.created", _job_event_payload(job))
    if get_settings().jobs_inline:
        await run_job(job.id)
        return
    from app.jobs.queue import get_arq_pool

    pool = await get_arq_pool()
    await pool.enqueue_job("run_job", str(job.id), _job_id=f"job:{job.id}:{job.attempt}")


async def run_job(job_id: uuid.UUID) -> None:
    """Executes one attempt of a job. Never raises — outcome is recorded on the row."""
    import app.jobs.handlers  # noqa: F401  (registers handlers)

    worker_name = f"{socket.gethostname()}:{os.getpid()}"
    async with session_scope() as session:
        job = await session.get(Job, job_id, with_for_update=True)
        if job is None:
            log.warning("job_missing", job_id=str(job_id))
            return
        if job.status not in (JobStatus.QUEUED, JobStatus.RETRYING):
            # Cancelled, already running elsewhere, or finished — duplicate delivery.
            await session.rollback()
            return
        job.status = JobStatus.RUNNING
        job.attempt += 1
        job.started_at = datetime.now(UTC)
        job.worker = worker_name
        job.next_retry_at = None
        await session.commit()
        await publish_event(job.workspace_id, "job.started", _job_event_payload(job))

    started = datetime.now(UTC)
    handler = _HANDLERS.get(job.job_type)
    outcome_status = JobStatus.SUCCESS
    error_code = error_message = None
    next_retry_at = None
    result: dict[str, Any] | None = None

    events: list[tuple[str, dict[str, Any]]] = []

    def emit(event_type: str, data: dict[str, Any]) -> None:
        events.append((event_type, data))

    try:
        if handler is None:
            raise JobFailed("NO_HANDLER", f"No handler registered for {job.job_type.value}")
        async with session_scope() as session:
            job_in_session = await session.get(Job, job_id)
            try:
                result = await handler(session, job_in_session, json.loads(job.payload_json or "{}"), emit)
                await session.commit()
            except (RetryLater, JobFailed):
                # Controlled outcomes: keep the state the handler recorded
                # (e.g. publication back to PENDING with its FloodWait info).
                await session.commit()
                raise
    except RetryLater as exc:
        outcome_status, error_code, error_message, next_retry_at = (
            JobStatus.RETRYING, exc.code, exc.message, exc.at,
        )
    except JobFailed as exc:
        outcome_status, error_code, error_message = JobStatus.FAILED, exc.code, exc.message
    except Exception as exc:
        log.exception("job_handler_crashed", job_id=str(job_id), job_type=job.job_type.value)
        events.clear()  # work was rolled back; don't announce it
        error_code, error_message = type(exc).__name__, str(exc)[:2000]
        if job.attempt < job.max_attempts:
            outcome_status, next_retry_at = JobStatus.RETRYING, datetime.now(UTC) + backoff_for(job.attempt)
        else:
            outcome_status = JobStatus.FAILED

    for event_type, data in events:
        await publish_event(job.workspace_id, event_type, data)

    finished = datetime.now(UTC)
    async with session_scope() as session:
        job = await session.get(Job, job_id)
        if job.status == JobStatus.CANCELLED:
            return
        job.status = outcome_status
        job.error_code = error_code
        job.error_message = error_message
        job.next_retry_at = next_retry_at
        if outcome_status == JobStatus.SUCCESS:
            job.progress = 100
        if result:
            meta = json.loads(job.metadata_json or "{}")
            meta.update(result)
            job.metadata_json = json.dumps(meta, default=str)
        if outcome_status in TERMINAL_STATUSES:
            job.finished_at = finished
        session.add(
            JobAttempt(
                job_id=job.id, attempt_number=job.attempt, status=outcome_status, error=error_message,
                started_at=started, finished_at=finished,
                duration_ms=int((finished - started).total_seconds() * 1000),
            )
        )
        await session.commit()
        event = {
            JobStatus.SUCCESS: "job.completed",
            JobStatus.FAILED: "job.failed",
            JobStatus.RETRYING: "job.progress",
        }[outcome_status]
        await publish_event(job.workspace_id, event, _job_event_payload(job))


async def set_progress(session: AsyncSession, job: Job, progress: int) -> None:
    job.progress = max(0, min(100, progress))
    await session.flush()
    await publish_event(job.workspace_id, "job.progress", _job_event_payload(job))
