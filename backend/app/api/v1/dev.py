"""Development-only controls for the fake providers (E2E tests).

Mounted only when the fake Telegram provider is active and APP_ENV is not
production — never reachable in a real deployment.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_workspace_member
from app.core.redis import get_redis
from app.models.identity import WorkspaceMember
from app.services.telegram.fake_provider import FAIL_ENTITIES_KEY

router = APIRouter(prefix="/workspaces/{workspace_id}/dev", tags=["dev"])


class FailuresRequest(BaseModel):
    entity_ids: list[int]


@router.put("/fake-telegram/failures")
async def set_fake_failures(
    workspace_id: uuid.UUID, payload: FailuresRequest, member: WorkspaceMember = Depends(get_workspace_member)
):
    redis = get_redis()
    await redis.delete(FAIL_ENTITIES_KEY)
    if payload.entity_ids:
        await redis.sadd(FAIL_ENTITIES_KEY, *[str(e) for e in payload.entity_ids])
    return {"failing_entity_ids": payload.entity_ids}
