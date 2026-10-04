from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_workspace_member
from app.core.errors import ApiError
from app.models.identity import User, WorkspaceMember
from app.models.ops import Notification

router = APIRouter(prefix="/workspaces/{workspace_id}/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    message: str
    metadata: dict
    read: bool
    created_at: datetime


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    unread: int


@router.get("", response_model=NotificationPage)
async def list_notifications(
    workspace_id: uuid.UUID, unread_only: bool = False, limit: int = Query(default=50, ge=1, le=200),
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    base = select(Notification).where(Notification.workspace_id == workspace_id, Notification.user_id == user.id)
    unread = await db.scalar(select(func.count()).select_from(base.where(Notification.read_at.is_(None)).subquery()))
    stmt = base.where(Notification.read_at.is_(None)) if unread_only else base
    rows = (await db.execute(stmt.order_by(Notification.created_at.desc()).limit(limit))).scalars().all()
    return NotificationPage(
        items=[NotificationOut(id=n.id, kind=n.kind, message=n.message, metadata=json.loads(n.metadata_json or "{}"),
                               read=n.read_at is not None, created_at=n.created_at) for n in rows],
        unread=unread or 0,
    )


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(workspace_id: uuid.UUID, notification_id: uuid.UUID,
                    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    n = await db.get(Notification, notification_id)
    if n is None or n.workspace_id != workspace_id or n.user_id != user.id:
        raise ApiError(404, "NOTIFICATION_NOT_FOUND", "Notification not found")
    n.read_at = n.read_at or datetime.now(UTC)
    await db.commit()


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member),
                        user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(update(Notification).where(
        Notification.workspace_id == workspace_id, Notification.user_id == user.id, Notification.read_at.is_(None),
    ).values(read_at=datetime.now(UTC)))
    await db.commit()
