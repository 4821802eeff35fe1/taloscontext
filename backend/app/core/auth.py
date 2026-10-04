from __future__ import annotations

import uuid

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import get_settings

SESSION_COOKIE_NAME = "channelos_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 14  # 14 days


def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    secret = settings.app_secret_key or "dev-insecure-secret-change-me"
    return URLSafeTimedSerializer(secret, salt="channelos-session")


def create_session_token(user_id: uuid.UUID) -> str:
    return _serializer().dumps({"user_id": str(user_id)})


def read_session_token(token: str) -> uuid.UUID | None:
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        return uuid.UUID(data["user_id"])
    except (BadSignature, SignatureExpired, KeyError, ValueError):
        return None
