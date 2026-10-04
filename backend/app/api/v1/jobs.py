from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_workspace_member
from app.models.identity import WorkspaceMember
from app.models.ops import Job

router = APIRouter(prefix="/workspaces/{workspace_id}/jobs", tags=["jobs"])


class JobResponse(BaseModel):
    id: uuid.UUID
    job_type: str
    status: str
    attempt: int
    max_attempts: int
    error: str | None


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Job).where(Job.workspace_id == workspace_id).order_by(Job.created_at.desc()).limit(100)
    )
    return [
        JobResponse(
            id=j.id, job_type=j.job_type.value, status=j.status.value,
            attempt=j.attempt, max_attempts=j.max_attempts, error=j.error,
        )
        for j in result.scalars().all()
    ]
