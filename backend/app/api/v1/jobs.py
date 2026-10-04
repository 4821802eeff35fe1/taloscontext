from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_workspace_member
from app.core.rbac import CAN_EDIT_CONTENT, require_role
from app.models.enums import JobStatus, JobType
from app.models.identity import User, WorkspaceMember
from app.models.ops import Job, JobAttempt
from app.services.audit.service import AuditService
from app.services.jobs.service import JobNotRetryableError, JobService, dispatch

router = APIRouter(prefix="/workspaces/{workspace_id}/jobs", tags=["jobs"])


class JobResponse(BaseModel):
    id: uuid.UUID
    job_type: str
    status: str
    progress: int
    entity_type: str | None
    entity_id: str | None
    payload_summary: str
    attempt: int
    max_attempts: int
    queued_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    next_retry_at: datetime | None
    worker: str | None
    error_code: str | None
    error_message: str | None
    metadata: dict
    created_at: datetime
    duration_ms: int | None

    @classmethod
    def from_model(cls, j: Job) -> JobResponse:
        duration = None
        if j.started_at and j.finished_at:
            duration = int((j.finished_at - j.started_at).total_seconds() * 1000)
        return cls(
            id=j.id, job_type=j.job_type.value, status=j.status.value, progress=j.progress or 0,
            entity_type=j.entity_type, entity_id=j.entity_id, payload_summary=j.payload_summary or "",
            attempt=j.attempt, max_attempts=j.max_attempts, queued_at=j.queued_at, started_at=j.started_at,
            finished_at=j.finished_at, next_retry_at=j.next_retry_at, worker=j.worker,
            error_code=j.error_code, error_message=j.error_message,
            metadata=json.loads(j.metadata_json or "{}"), created_at=j.created_at, duration_ms=duration,
        )


class AttemptResponse(BaseModel):
    attempt_number: int
    status: str
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None


class JobDetailResponse(JobResponse):
    attempts: list[AttemptResponse]


class JobPage(BaseModel):
    items: list[JobResponse]
    next_cursor: str | None
    counts: dict[str, int]


def _encode_cursor(job: Job) -> str:
    return base64.urlsafe_b64encode(f"{job.created_at.isoformat()}|{job.id}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        stamp, job_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(stamp), uuid.UUID(job_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid cursor") from exc


async def _get_job(db: AsyncSession, workspace_id: uuid.UUID, job_id: uuid.UUID) -> Job:
    job = await db.get(Job, job_id, with_for_update=True)
    if job is None or job.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job


@router.get("", response_model=JobPage)
async def list_jobs(
    workspace_id: uuid.UUID,
    status_filter: list[JobStatus] | None = Query(default=None, alias="status"),
    job_type: list[JobType] | None = Query(default=None, alias="type"),
    q: str | None = Query(default=None, max_length=200),
    entity_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    member: WorkspaceMember = Depends(get_workspace_member),
    db: AsyncSession = Depends(get_db),
):
    base = select(Job).where(Job.workspace_id == workspace_id)
    if job_type:
        base = base.where(Job.job_type.in_(job_type))
    if entity_id:
        base = base.where(Job.entity_id == entity_id)
    if q:
        pattern = f"%{q.lower()}%"
        base = base.where(
            or_(func.lower(Job.payload_summary).like(pattern), func.lower(Job.error_message).like(pattern))
        )

    sub = base.subquery()
    count_rows = await db.execute(select(sub.c.status, func.count()).group_by(sub.c.status))
    counts = {(st.value if hasattr(st, "value") else str(st)): n for st, n in count_rows.all()}

    stmt = base
    if status_filter:
        stmt = stmt.where(Job.status.in_(status_filter))
    if cursor:
        stamp, last_id = _decode_cursor(cursor)
        stmt = stmt.where(or_(Job.created_at < stamp, and_(Job.created_at == stamp, Job.id < last_id)))
    rows = (await db.execute(stmt.order_by(Job.created_at.desc(), Job.id.desc()).limit(limit + 1))).scalars().all()
    next_cursor = _encode_cursor(rows[limit - 1]) if len(rows) > limit else None
    return JobPage(items=[JobResponse.from_model(j) for j in rows[:limit]], next_cursor=next_cursor, counts=counts)


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job(
    workspace_id: uuid.UUID, job_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    job = await _get_job(db, workspace_id, job_id)
    attempts = (
        await db.execute(select(JobAttempt).where(JobAttempt.job_id == job.id).order_by(JobAttempt.attempt_number))
    ).scalars().all()
    return JobDetailResponse(
        **JobResponse.from_model(job).model_dump(),
        attempts=[
            AttemptResponse(
                attempt_number=a.attempt_number, status=a.status.value, error=a.error,
                started_at=a.started_at, finished_at=a.finished_at, duration_ms=a.duration_ms,
            )
            for a in attempts
        ],
    )


@router.post("/{job_id}/retry", response_model=JobResponse)
async def retry_job(
    workspace_id: uuid.UUID, job_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    job = await _get_job(db, workspace_id, job_id)
    try:
        await JobService(db).retry(job)
    except JobNotRetryableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await AuditService(db).record(
        workspace_id=workspace_id, actor_user_id=user.id, action="job.retried", entity_type="job",
        entity_id=job.id, metadata={"type": job.job_type.value},
    )
    await db.commit()
    await dispatch(job)
    await db.refresh(job)
    return JobResponse.from_model(job)


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    workspace_id: uuid.UUID, job_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    job = await _get_job(db, workspace_id, job_id)
    try:
        await JobService(db).cancel(job)
    except JobNotRetryableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await AuditService(db).record(
        workspace_id=workspace_id, actor_user_id=user.id, action="job.cancelled", entity_type="job", entity_id=job.id,
    )
    await db.commit()
    from app.services.jobs.service import _job_event_payload
    from app.services.realtime.events import publish_event

    await publish_event(workspace_id, "job.cancelled", _job_event_payload(job))
    return JobResponse.from_model(job)
