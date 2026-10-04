from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import WorkspaceSettings


async def get_workspace_settings(session: AsyncSession, workspace_id: uuid.UUID) -> WorkspaceSettings:
    """Returns the workspace's settings row, creating it with defaults on first use."""
    row = (
        await session.execute(select(WorkspaceSettings).where(WorkspaceSettings.workspace_id == workspace_id))
    ).scalar_one_or_none()
    if row is None:
        row = WorkspaceSettings(
            workspace_id=workspace_id, timezone="UTC", cta_defaults_json="{}",
            misfire_policy="RESCHEDULE_NEXT_SLOT", misfire_grace_minutes=15, notification_prefs_json="{}",
        )
        session.add(row)
        await session.flush()
    return row


async def cta_defaults(session: AsyncSession, workspace_id: uuid.UUID) -> dict[str, str]:
    row = await get_workspace_settings(session, workspace_id)
    try:
        value = json.loads(row.cta_defaults_json or "{}")
    except json.JSONDecodeError:
        return {}
    return {str(k): str(v) for k, v in value.items() if v} if isinstance(value, dict) else {}
