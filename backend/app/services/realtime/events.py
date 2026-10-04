"""Realtime event bus.

Any process (API, worker, scheduler) publishes to a per-workspace Redis
pub/sub channel; the API's SSE endpoint fans those out to connected browsers.
Publishing never raises into business logic — a lost event only means a UI
refresh happens on the next poll/refetch instead of instantly.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from app.core.redis import get_redis

log = structlog.get_logger(__name__)

EVENT_TYPES = {
    "job.created", "job.started", "job.progress", "job.completed", "job.failed", "job.cancelled",
    "content.generated", "content.updated", "content.approved", "content.scheduled",
    "publication.started", "publication.published", "publication.failed", "publication.retry_scheduled",
    "telegram.account.health_changed", "telegram.auth.updated",
    "budget.warning", "budget.exceeded",
    "media.created", "notification.created",
}


def channel_for(workspace_id: uuid.UUID | str) -> str:
    return f"events:{workspace_id}"


async def publish_event(workspace_id: uuid.UUID | str, event_type: str, data: dict[str, Any] | None = None) -> None:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown event type {event_type}")
    payload = json.dumps(
        {"type": event_type, "data": data or {}, "ts": datetime.now(UTC).isoformat()},
        default=str,
    )
    try:
        await get_redis().publish(channel_for(workspace_id), payload)
    except Exception as exc:  # noqa: BLE001
        log.warning("event_publish_failed", event_type=event_type, error=type(exc).__name__)
