"""Dependency and process health.

Worker and scheduler prove liveness by writing heartbeat keys to Redis; a
missing or stale heartbeat means the process is down even if Redis is fine.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from sqlalchemy import text

from app.core.redis import get_redis

HEARTBEAT_STALE_SECONDS = 90
WORKER_HEARTBEAT_KEY = "heartbeat:worker"
SCHEDULER_HEARTBEAT_KEY = "heartbeat:scheduler"


async def beat(key: str, ttl: int = 300) -> None:
    await get_redis().set(key, str(int(time.time())), ex=ttl)


async def _postgres() -> dict[str, Any]:
    from app.db.session import session_scope

    try:
        async with session_scope() as session:
            await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=3)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": type(exc).__name__}


async def _redis() -> dict[str, Any]:
    try:
        await asyncio.wait_for(get_redis().ping(), timeout=3)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": type(exc).__name__}


async def _heartbeat(key: str) -> dict[str, Any]:
    try:
        raw = await get_redis().get(key)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": type(exc).__name__}
    if raw is None:
        return {"ok": False, "error": "no heartbeat"}
    age = int(time.time()) - int(raw)
    return {"ok": age <= HEARTBEAT_STALE_SECONDS, "last_seen_seconds_ago": age}


async def _s3() -> dict[str, Any]:
    from app.services.media.storage import MediaStorage

    try:
        storage = MediaStorage()
        await asyncio.wait_for(asyncio.to_thread(storage.head_bucket), timeout=5)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": type(exc).__name__}


async def readiness() -> dict[str, dict[str, Any]]:
    postgres, redis, s3, worker, scheduler = await asyncio.gather(
        _postgres(), _redis(), _s3(), _heartbeat(WORKER_HEARTBEAT_KEY), _heartbeat(SCHEDULER_HEARTBEAT_KEY)
    )
    return {"postgres": postgres, "redis": redis, "s3": s3, "worker": worker, "scheduler": scheduler}
