from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import Cookie, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    LAST_SEEN_RESOLUTION,
    SESSION_COOKIE_NAME,
    read_session_id,
    session_is_valid,
)
from app.core.errors import ApiError
from app.db.session import get_session
from app.models.identity import User, UserSession, WorkspaceMember


async def get_db(session: AsyncSession = Depends(get_session)) -> AsyncGenerator[AsyncSession, None]:
    yield session


async def get_current_session(
    request: Request,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> UserSession:
    if not session_token:
        raise ApiError(401, "AUTH_REQUIRED", "Not signed in")
    session_id = read_session_id(session_token)
    row = await db.get(UserSession, session_id) if session_id else None
    now = datetime.now(UTC)
    if not session_is_valid(row, now):
        raise ApiError(401, "AUTH_SESSION_EXPIRED", "Your session has expired. Sign in again.")
    last_seen = row.last_seen_at if row.last_seen_at.tzinfo else row.last_seen_at.replace(tzinfo=UTC)
    if now - last_seen > LAST_SEEN_RESOLUTION:
        row.last_seen_at = now
        await db.commit()
    request.state.session_id = row.id
    return row


async def get_current_user(
    session_row: UserSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.get(User, session_row.user_id)
    if not user or not user.is_active:
        raise ApiError(401, "AUTH_ACCOUNT_DISABLED", "This account is disabled.")
    return user


async def get_workspace_member(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMember:
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user.id
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        # 404, not 403: don't confirm that a workspace id exists to non-members.
        raise ApiError(404, "WORKSPACE_ACCESS_DENIED", "Workspace not found")
    return member
