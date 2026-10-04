"""Owned, renewed Redis leases for cross-process operations."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress


@asynccontextmanager
async def lease(redis, key: str, *, seconds: int = 60):
    lock = redis.lock(key, timeout=seconds, blocking=False, thread_local=False)
    acquired = await lock.acquire()
    if not acquired:
        yield False
        return
    owner = asyncio.current_task()

    async def renew():
        try:
            while True:
                await asyncio.sleep(seconds / 3)
                await lock.extend(seconds, replace_ttl=True)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — lease failure must cancel its owner
            owner.cancel()

    renewal = asyncio.create_task(renew())
    try:
        yield True
    finally:
        renewal.cancel()
        with suppress(asyncio.CancelledError):
            await renewal
        if await lock.owned():
            await lock.release()
