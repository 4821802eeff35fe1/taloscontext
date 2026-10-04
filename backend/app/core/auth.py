"""Cookie session handling.

The cookie holds a signed, timed token wrapping a server-side session id
(`user_sessions` row). Signing stops tampering; the DB row makes sessions
revocable and gives an idle timeout. A fresh session id is minted on every
login, so a pre-set cookie can never be "upgraded" (session fixation).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.identity import UserSession

SESSION_COOKIE_NAME = "channelos_session"
IDLE_TIMEOUT = timedelta(days=3)
LAST_SEEN_RESOLUTION = timedelta(minutes=5)


def session_max_age() -> int:
    return get_settings().session_max_age_seconds


def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    secret = settings.app_secret_key or "dev-insecure-secret-change-me"
    return URLSafeTimedSerializer(secret, salt="channelos-session")


def sign_session_id(session_id: uuid.UUID) -> str:
    return _serializer().dumps({"sid": str(session_id)})


def read_session_id(token: str) -> uuid.UUID | None:
    try:
        data = _serializer().loads(token, max_age=session_max_age())
        return uuid.UUID(data["sid"])
    except (BadSignature, SignatureExpired, KeyError, ValueError, TypeError):
        return None


async def create_session(db: AsyncSession, user_id: uuid.UUID, *, ip: str, user_agent: str) -> UserSession:
    now = datetime.now(UTC)
    row = UserSession(
        user_id=user_id,
        expires_at=now + timedelta(seconds=session_max_age()),
        last_seen_at=now,
        ip_address=ip[:64],
        user_agent=user_agent[:300],
    )
    db.add(row)
    await db.flush()
    return row


def session_is_valid(row: UserSession | None, now: datetime) -> bool:
    if row is None or row.revoked_at is not None:
        return False
    expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    last_seen = row.last_seen_at if row.last_seen_at.tzinfo else row.last_seen_at.replace(tzinfo=UTC)
    return expires_at > now and now - last_seen < IDLE_TIMEOUT


async def revoke_all(db: AsyncSession, user_id: uuid.UUID, *, except_id: uuid.UUID | None = None) -> None:
    stmt = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_id is not None:
        stmt = stmt.where(UserSession.id != except_id)
    await db.execute(stmt.values(revoked_at=datetime.now(UTC)))
