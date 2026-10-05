"""Global search for the command palette: posts, channels, channel sets."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_workspace_member
from app.models.content import ContentItem
from app.models.identity import WorkspaceMember
from app.models.telegram import ChannelSet, TelegramChannel

router = APIRouter(prefix="/workspaces/{workspace_id}/search", tags=["search"])


class SearchResult(BaseModel):
    kind: str  # post|channel|channel_set
    id: uuid.UUID
    title: str
    subtitle: str
    # Machine-readable status/mode so clients can localize them.
    status: str | None = None


@router.get("", response_model=list[SearchResult])
async def search(workspace_id: uuid.UUID, q: str = Query(min_length=1, max_length=100),
                 member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db)):
    pattern = f"%{q.lower()}%"
    posts = (await db.execute(
        select(ContentItem).where(
            ContentItem.workspace_id == workspace_id, ContentItem.deleted_at.is_(None),
            or_(func.lower(ContentItem.title).like(pattern), func.lower(ContentItem.plain_text).like(pattern),
                func.lower(ContentItem.topic).like(pattern)),
        ).order_by(ContentItem.updated_at.desc()).limit(8)
    )).scalars().all()
    channels = (await db.execute(
        select(TelegramChannel).where(
            TelegramChannel.workspace_id == workspace_id,
            or_(func.lower(TelegramChannel.title).like(pattern), func.lower(TelegramChannel.username).like(pattern)),
        ).limit(6)
    )).scalars().all()
    sets = (await db.execute(
        select(ChannelSet).where(ChannelSet.workspace_id == workspace_id, func.lower(ChannelSet.name).like(pattern)).limit(6)
    )).scalars().all()
    return (
        [SearchResult(kind="post", id=p.id, title=p.title or p.topic or "",
                      subtitle=(p.plain_text or "")[:60], status=p.status.value) for p in posts]
        + [SearchResult(kind="channel", id=c.id, title=c.title, subtitle=f"@{c.username}" if c.username else "private")
           for c in channels]
        + [SearchResult(kind="channel_set", id=s.id, title=s.name, subtitle="", status=s.mode.value)
           for s in sets]
    )
