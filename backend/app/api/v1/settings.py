from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_workspace_member
from app.core.config import get_settings
from app.models.identity import WorkspaceMember
from app.services.ai.factory import get_image_provider, get_text_provider

router = APIRouter(prefix="/workspaces/{workspace_id}/settings", tags=["settings"])


class AIStatusResponse(BaseModel):
    text_provider: str
    text_provider_is_fake: bool
    image_provider: str
    image_provider_status: str
    image_provider_is_fake: bool
    telegram_provider_is_fake: bool


@router.get("/ai-status", response_model=AIStatusResponse)
async def ai_status(
    workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member)
):
    app_settings = get_settings()
    text_provider = get_text_provider()
    image_provider = get_image_provider()
    image_status = await image_provider.status()
    return AIStatusResponse(
        text_provider=text_provider.name,
        text_provider_is_fake=app_settings.use_fake_ai_provider,
        image_provider=image_provider.name,
        image_provider_status=image_status.value,
        image_provider_is_fake=app_settings.use_fake_image_provider,
        telegram_provider_is_fake=app_settings.use_fake_telegram_provider,
    )
