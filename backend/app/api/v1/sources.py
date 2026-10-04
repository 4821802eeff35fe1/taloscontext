from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_workspace_member
from app.core.rbac import CAN_EDIT_CONTENT, require_role
from app.jobs.queue import get_arq_pool
from app.models.identity import WorkspaceMember
from app.models.sources import Source, SourceItem

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["sources"])


class SourceCreateRequest(BaseModel):
    kind: str
    name: str
    config: dict = {}


class SourceResponse(BaseModel):
    id: uuid.UUID
    kind: str
    name: str
    is_active: bool


class IdeaResponse(BaseModel):
    id: uuid.UUID
    title: str
    summary: str
    url: str
    url_verified: bool
    status: str
    category: str


@router.get("/sources", response_model=list[SourceResponse])
async def list_sources(
    workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Source).where(Source.workspace_id == workspace_id))
    return [SourceResponse(id=s.id, kind=s.kind, name=s.name, is_active=s.is_active) for s in result.scalars().all()]


@router.post("/sources", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    workspace_id: uuid.UUID, payload: SourceCreateRequest,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    source = Source(
        workspace_id=workspace_id, kind=payload.kind, name=payload.name,
        config_json=json.dumps(payload.config, ensure_ascii=False),
    )
    db.add(source)
    await db.commit()

    if source.kind == "rss":
        pool = await get_arq_pool()
        await pool.enqueue_job("source_fetch", str(source.id))

    return SourceResponse(id=source.id, kind=source.kind, name=source.name, is_active=source.is_active)


@router.get("/ideas", response_model=list[IdeaResponse])
async def list_ideas(
    workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(SourceItem).where(SourceItem.workspace_id == workspace_id).order_by(SourceItem.created_at.desc()).limit(100)
    )
    return [
        IdeaResponse(
            id=i.id, title=i.title, summary=i.summary, url=i.url,
            url_verified=i.url_verified, status=i.status.value, category=i.category,
        )
        for i in result.scalars().all()
    ]
