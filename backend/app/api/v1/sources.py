from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_workspace_member
from app.api.v1.jobs import JobResponse
from app.core.rbac import CAN_EDIT_CONTENT, require_role
from app.models.enums import IdeaStatus, JobType
from app.models.identity import User, WorkspaceMember
from app.models.sources import Source, SourceItem
from app.models.telegram import TelegramAccount
from app.services.audit.service import AuditService
from app.services.content.source_service import SOURCE_KINDS
from app.services.jobs.service import JobService, dispatch
from app.services.security.ssrf_guard import SSRFBlockedError, assert_url_is_safe

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["sources"])


class SourceConfig(BaseModel):
    url: str | None = Field(default=None, max_length=2000)
    channel: str | None = Field(default=None, max_length=100)
    account_id: uuid.UUID | None = None
    keywords: list[str] = Field(default_factory=list, max_length=50)
    category: str = Field(default="news", max_length=100)
    fetch_interval_minutes: int = Field(default=60, ge=10, le=24 * 60)


class SourceCreateRequest(BaseModel):
    kind: str
    name: str = Field(min_length=1, max_length=300)
    config: SourceConfig = Field(default_factory=SourceConfig)
    enabled: bool = True

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if v not in SOURCE_KINDS:
            raise ValueError(f"kind must be one of {', '.join(SOURCE_KINDS)}")
        return v


class SourceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    config: SourceConfig | None = None
    enabled: bool | None = None


class SourceResponse(BaseModel):
    id: uuid.UUID
    kind: str
    name: str
    enabled: bool
    config: dict
    last_fetched_at: datetime | None
    last_success_at: str | None
    last_error: str | None
    items_total: int
    items_new: int


class IdeaResponse(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    source_name: str
    title: str
    summary: str
    url: str
    url_verified: bool
    published_at: datetime | None
    freshness: float
    relevance: float
    status: str
    category: str
    created_at: datetime


class IdeaPage(BaseModel):
    items: list[IdeaResponse]
    counts: dict[str, int]


class IdeaUpdateRequest(BaseModel):
    status: IdeaStatus


def _validate_config(kind: str, config: SourceConfig) -> None:
    if kind in ("rss", "url", "manual"):
        if not config.url:
            raise HTTPException(422, "This source needs a URL.")
        try:
            assert_url_is_safe(config.url)
        except SSRFBlockedError as exc:
            raise HTTPException(422, f"URL not allowed: {exc}") from exc
    if kind == "telegram" and not (config.channel and config.account_id):
        raise HTTPException(422, "Pick a channel username and a connected account.")


async def _source_or_404(db: AsyncSession, workspace_id: uuid.UUID, source_id: uuid.UUID) -> Source:
    source = await db.get(Source, source_id)
    if source is None or source.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
    return source


async def _responses(db: AsyncSession, sources: list[Source]) -> list[SourceResponse]:
    ids = [s.id for s in sources]
    totals = dict((await db.execute(select(SourceItem.source_id, func.count()).where(SourceItem.source_id.in_(ids))
                                    .group_by(SourceItem.source_id))).all()) if ids else {}
    new = dict((await db.execute(select(SourceItem.source_id, func.count()).where(
        SourceItem.source_id.in_(ids), SourceItem.status == IdeaStatus.NEW).group_by(SourceItem.source_id))).all()) if ids else {}
    out = []
    for s in sources:
        cfg = json.loads(s.config_json or "{}")
        out.append(SourceResponse(
            id=s.id, kind=s.kind, name=s.name, enabled=s.is_active,
            config={k: v for k, v in cfg.items() if k not in ("last_error", "last_success_at")},
            last_fetched_at=s.last_fetched_at, last_success_at=cfg.get("last_success_at"),
            last_error=cfg.get("last_error"), items_total=totals.get(s.id, 0), items_new=new.get(s.id, 0),
        ))
    return out


@router.get("/sources", response_model=list[SourceResponse])
async def list_sources(
    workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db)
):
    sources = (await db.execute(select(Source).where(Source.workspace_id == workspace_id).order_by(Source.created_at))).scalars().all()
    return await _responses(db, list(sources))


@router.post("/sources", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    workspace_id: uuid.UUID, payload: SourceCreateRequest,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    _validate_config(payload.kind, payload.config)
    if payload.config.account_id:
        account = await db.get(TelegramAccount, payload.config.account_id)
        if account is None or account.workspace_id != workspace_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Telegram account not found")
    source = Source(workspace_id=workspace_id, kind=payload.kind, name=payload.name, is_active=payload.enabled,
                    config_json=payload.config.model_dump_json())
    db.add(source)
    await db.flush()
    job = await JobService(db).create(
        workspace_id=workspace_id, job_type=JobType.SOURCE_FETCH, payload={"source_id": str(source.id)},
        entity_type="source", entity_id=source.id, summary=f"Fetch {source.name}", created_by_user_id=user.id,
        max_attempts=3,
    ) if payload.enabled else None
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="source.created",
                                  entity_type="source", entity_id=source.id, metadata={"kind": source.kind, "name": source.name})
    await db.commit()
    if job:
        await dispatch(job)
    await db.refresh(source)
    return (await _responses(db, [source]))[0]


@router.patch("/sources/{source_id}", response_model=SourceResponse)
async def update_source(
    workspace_id: uuid.UUID, source_id: uuid.UUID, payload: SourceUpdateRequest,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    source = await _source_or_404(db, workspace_id, source_id)
    if payload.name is not None:
        source.name = payload.name
    if payload.enabled is not None:
        source.is_active = payload.enabled
    if payload.config is not None:
        _validate_config(source.kind, payload.config)
        if payload.config.account_id:
            account = await db.get(TelegramAccount, payload.config.account_id)
            if account is None or account.workspace_id != workspace_id:
                raise HTTPException(404, "Telegram account not found")
        old = json.loads(source.config_json or "{}")
        new = payload.config.model_dump(mode="json")
        new.update({k: old[k] for k in ("last_error", "last_success_at") if k in old})
        source.config_json = json.dumps(new)
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="source.updated",
                                  entity_type="source", entity_id=source.id)
    await db.commit()
    return (await _responses(db, [source]))[0]


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    workspace_id: uuid.UUID, source_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    source = await _source_or_404(db, workspace_id, source_id)
    await db.delete(source)
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="source.deleted",
                                  entity_type="source", entity_id=source_id, metadata={"name": source.name})
    await db.commit()


@router.post("/sources/{source_id}/fetch", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def fetch_now(
    workspace_id: uuid.UUID, source_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    source = await _source_or_404(db, workspace_id, source_id)
    service = JobService(db)
    if (active := await service.active_for_entity("source", source.id)) is not None:
        return JobResponse.from_model(active)
    job = await service.create(
        workspace_id=workspace_id, job_type=JobType.SOURCE_FETCH, payload={"source_id": str(source.id)},
        entity_type="source", entity_id=source.id, summary=f"Fetch {source.name}", created_by_user_id=user.id,
        max_attempts=3,
    )
    await db.commit()
    await dispatch(job)
    await db.refresh(job)
    return JobResponse.from_model(job)


@router.get("/ideas", response_model=IdeaPage)
async def list_ideas(
    workspace_id: uuid.UUID,
    status_filter: list[IdeaStatus] | None = Query(default=None, alias="status"),
    source_id: uuid.UUID | None = None,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=300),
    member: WorkspaceMember = Depends(get_workspace_member),
    db: AsyncSession = Depends(get_db),
):
    base = select(SourceItem).where(SourceItem.workspace_id == workspace_id)
    if source_id:
        base = base.where(SourceItem.source_id == source_id)
    if q:
        pattern = f"%{q.lower()}%"
        base = base.where(or_(func.lower(SourceItem.title).like(pattern), func.lower(SourceItem.summary).like(pattern)))
    sub = base.subquery()
    counts = {(s.value if hasattr(s, "value") else str(s)): n
              for s, n in (await db.execute(select(sub.c.status, func.count()).group_by(sub.c.status))).all()}
    stmt = base.where(SourceItem.status.in_(status_filter)) if status_filter else base
    rows = (await db.execute(
        stmt.order_by(SourceItem.relevance_score.desc(), SourceItem.freshness_score.desc(), SourceItem.created_at.desc())
        .limit(limit)
    )).scalars().all()
    names = dict((await db.execute(select(Source.id, Source.name).where(Source.workspace_id == workspace_id))).all())
    return IdeaPage(
        items=[
            IdeaResponse(
                id=i.id, source_id=i.source_id, source_name=names.get(i.source_id, ""), title=i.title,
                summary=i.summary, url=i.url, url_verified=i.url_verified, published_at=i.published_at,
                freshness=i.freshness_score, relevance=i.relevance_score, status=i.status.value,
                category=i.category, created_at=i.created_at,
            )
            for i in rows
        ],
        counts=counts,
    )


@router.patch("/ideas/{idea_id}", response_model=IdeaResponse)
async def update_idea(
    workspace_id: uuid.UUID, idea_id: uuid.UUID, payload: IdeaUpdateRequest,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    idea = await db.get(SourceItem, idea_id)
    if idea is None or idea.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Idea not found")
    idea.status = payload.status
    await db.commit()
    source = await db.get(Source, idea.source_id)
    return IdeaResponse(
        id=idea.id, source_id=idea.source_id, source_name=source.name if source else "", title=idea.title,
        summary=idea.summary, url=idea.url, url_verified=idea.url_verified, published_at=idea.published_at,
        freshness=idea.freshness_score, relevance=idea.relevance_score, status=idea.status.value,
        category=idea.category, created_at=idea.created_at,
    )
