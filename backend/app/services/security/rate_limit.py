"""Redis fixed-window rate limiting for auth-sensitive endpoints.

Windows expire on their own — nothing is ever locked permanently. Limits
apply to *attempts*, regardless of outcome, so the response can't be used to
learn whether an email exists.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from starlette.requests import Request

from app.core.config import get_settings
from app.core.redis import get_redis


@dataclass(frozen=True)
class Limit:
    name: str
    max_attempts: int
    window_seconds: int


LOGIN_PER_IP = Limit("login_ip", 5, 5 * 60)
LOGIN_PER_ACCOUNT = Limit("login_account", 10, 30 * 60)
REGISTER_PER_IP = Limit("register_ip", 5, 60 * 60)
TG_CODE_PER_FLOW = Limit("tg_code_flow", 5, 10 * 60)
TG_CODE_PER_IP = Limit("tg_code_ip", 20, 10 * 60)
TG_PASSWORD_PER_FLOW = Limit("tg_password_flow", 5, 10 * 60)
TG_PASSWORD_PER_IP = Limit("tg_password_ip", 20, 10 * 60)
TG_START_PER_WORKSPACE = Limit("tg_start_ws", 10, 60 * 60)


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        super().__init__(f"Too many attempts. Try again in {retry_after} seconds.")
        self.retry_after = retry_after


def client_ip(request: Request) -> str:
    trusted = get_settings().trusted_proxy_count
    if trusted > 0:
        forwarded = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(forwarded) >= trusted:
            return forwarded[-trusted]
    return request.client.host if request.client else "unknown"


def _bucket(limit: Limit, subject: str) -> str:
    digest = hashlib.sha256(subject.lower().encode()).hexdigest()[:32]  # no raw emails/IPs in Redis keys
    return f"rl:{limit.name}:{digest}"


async def hit(limit: Limit, subject: str) -> None:
    """Counts one attempt; raises RateLimitExceeded once over the limit."""
    redis = get_redis()
    key = _bucket(limit, subject)
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, limit.window_seconds, nx=True)
    pipe.ttl(key)
    count, _, ttl = await pipe.execute()
    if count > limit.max_attempts:
        raise RateLimitExceeded(max(1, int(ttl)))


async def hit_all(*pairs: tuple[Limit, str]) -> None:
    # Count every bucket before raising so one limit can't be used to dodge another.
    exceeded: list[RateLimitExceeded] = []
    for limit, subject in pairs:
        try:
            await hit(limit, subject)
        except RateLimitExceeded as exc:
            exceeded.append(exc)
    if exceeded:
        raise max(exceeded, key=lambda e: e.retry_after)


async def reset(limit: Limit, subject: str) -> None:
    await get_redis().delete(_bucket(limit, subject))
