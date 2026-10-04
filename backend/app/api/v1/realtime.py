"""Server-Sent Events stream of workspace events.

Workers/scheduler publish to Redis; each connected browser gets its own
subscription here. EventSource reconnects automatically; the client also
re-fetches its queries on reconnect, so events missed while offline are
covered by fresh data rather than a replay log.
"""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_workspace_member
from app.core.redis import get_redis
from app.models.identity import WorkspaceMember
from app.services.realtime.events import channel_for

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["realtime"])

HEARTBEAT_SECONDS = 15


async def event_stream(request: Request, workspace_id: uuid.UUID, *, max_idle_loops: int | None = None):
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(channel_for(workspace_id))
    try:
        yield "retry: 3000\n\n"  # client reconnect delay hint
        yield 'event: ready\ndata: {"type":"ready"}\n\n'
        idle = 0
        while True:
            if await request.is_disconnected():
                break
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=HEARTBEAT_SECONDS)
            if message is None:
                idle += 1
                if max_idle_loops is not None and idle >= max_idle_loops:
                    break
                yield ": keep-alive\n\n"
                continue
            idle = 0
            data = message["data"]
            if isinstance(data, bytes):
                data = data.decode()
            yield f"data: {data}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe()
        await pubsub.aclose()


@router.get("/events")
async def events(
    workspace_id: uuid.UUID, request: Request, member: WorkspaceMember = Depends(get_workspace_member)
):
    return StreamingResponse(
        event_stream(request, workspace_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
