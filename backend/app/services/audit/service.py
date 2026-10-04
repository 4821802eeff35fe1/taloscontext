from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import REDACTED_KEYS
from app.models.ops import AuditLog


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("***REDACTED***" if k.lower() in REDACTED_KEYS else _scrub(v)) for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


class AuditService:
    """Append-only audit trail. Metadata is scrubbed with the same key list as
    the log redactor so a careless caller can't persist a secret here either."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID | str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLog:
        row = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else "",
            metadata_json=json.dumps(_scrub(metadata or {}), ensure_ascii=False, default=str),
        )
        self.session.add(row)
        await self.session.flush()
        return row
