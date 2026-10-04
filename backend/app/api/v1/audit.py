from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_workspace_member
from app.core.errors import ApiError
from app.core.rbac import CAN_MANAGE_SETTINGS, require_role
from app.models.identity import User, WorkspaceMember
from app.models.ops import AuditLog

router = APIRouter(prefix="/workspaces/{workspace_id}/audit", tags=["audit"])


class AuditOut(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_name: str
    action: str
    entity_type: str
    entity_id: str
    metadata: dict
    created_at: datetime


class AuditPage(BaseModel):
    items: list[AuditOut]
    next_cursor: str | None
    actions: list[str]


@router.get("", response_model=AuditPage)
async def list_audit(
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    action: str | None = Query(default=None, max_length=200),
    entity_type: str | None = Query(default=None, max_length=100),
    entity_id: str | None = Query(default=None, max_length=100),
    since: datetime | None = None,
    until: datetime | None = None,
    q: str | None = Query(default=None, max_length=200),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    member: WorkspaceMember = Depends(get_workspace_member),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_MANAGE_SETTINGS)  # audit is admin-only
    stmt = select(AuditLog).where(AuditLog.workspace_id == workspace_id)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_user_id == actor_id)
    if action:
        # "content" matches content.*; an exact action matches itself
        stmt = stmt.where(or_(AuditLog.action == action, AuditLog.action.like(f"{action}.%")))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if since:
        stmt = stmt.where(AuditLog.created_at >= since)
    if until:
        stmt = stmt.where(AuditLog.created_at < until)
    if q:
        stmt = stmt.where(func.lower(AuditLog.metadata_json).like(f"%{q.lower()}%"))
    if cursor:
        try:
            stamp, last = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
            stamp_dt, last_id = datetime.fromisoformat(stamp), uuid.UUID(last)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ApiError(400, "INVALID_CURSOR", "Invalid cursor") from exc
        stmt = stmt.where(or_(AuditLog.created_at < stamp_dt, and_(AuditLog.created_at == stamp_dt, AuditLog.id < last_id)))
    rows = (await db.execute(stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit + 1))).scalars().all()
    page = rows[:limit]
    actor_ids = {r.actor_user_id for r in page if r.actor_user_id}
    names = {uid: (name or email) for uid, name, email in (await db.execute(
        select(User.id, User.full_name, User.email).where(User.id.in_(actor_ids)))).all()} if actor_ids else {}
    actions = sorted({a for (a,) in (await db.execute(
        select(AuditLog.action).where(AuditLog.workspace_id == workspace_id).distinct())).all()})
    next_cursor = None
    if len(rows) > limit:
        last = page[-1]
        next_cursor = base64.urlsafe_b64encode(f"{last.created_at.isoformat()}|{last.id}".encode()).decode()
    return AuditPage(
        items=[AuditOut(id=r.id, actor_id=r.actor_user_id,
                        actor_name=names.get(r.actor_user_id, "Unknown user") if r.actor_user_id else "System",
                        action=r.action, entity_type=r.entity_type, entity_id=r.entity_id,
                        metadata=json.loads(r.metadata_json or "{}"), created_at=r.created_at) for r in page],
        next_cursor=next_cursor, actions=actions,
    )
