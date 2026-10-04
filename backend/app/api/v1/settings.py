"""Workspace settings. Secrets are never returned — only whether they're
configured and, for API keys, the last 4 characters."""
from __future__ import annotations

import json
import re
import uuid
from decimal import Decimal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_workspace_member
from app.core.auth import IDLE_TIMEOUT, session_max_age
from app.core.config import get_settings
from app.core.rbac import CAN_MANAGE_SETTINGS, require_role
from app.jobs.scheduler import MISFIRE_POLICIES
from app.models.identity import User, Workspace, WorkspaceMember
from app.services.ai.factory import get_image_provider, get_text_provider
from app.services.audit.service import AuditService
from app.services.content.cta_resolver import KNOWN_CTA_KEYS
from app.services.costs.service import CostService, get_pricing_snapshot
from app.services.scheduling.service import ScheduleValidationError, validate_timezone
from app.services.settings.service import get_workspace_settings

router = APIRouter(prefix="/workspaces/{workspace_id}/settings", tags=["settings"])


def mask_secret(value: str) -> str | None:
    if not value:
        return None
    return "••••••••" + value[-4:] if len(value) > 8 else "••••••••"


def mask_agent_url(url: str) -> str:
    return re.sub(r"(agents/)([0-9a-f]{4})[0-9a-f-]+([0-9a-f]{4})", r"\1\2…\3", url)


class AIStatusResponse(BaseModel):
    text_provider: str
    text_provider_is_fake: bool
    image_provider: str
    image_provider_status: str
    image_provider_is_fake: bool
    telegram_provider_is_fake: bool


class GeneralIn(BaseModel):
    workspace_name: str = Field(min_length=1, max_length=200)
    timezone: str = "UTC"
    misfire_policy: str = "RESCHEDULE_NEXT_SLOT"
    misfire_grace_minutes: int = Field(default=15, ge=1, le=24 * 60)
    cta_defaults: dict[str, str] = Field(default_factory=dict)

    @field_validator("misfire_policy")
    @classmethod
    def _policy(cls, v: str) -> str:
        if v not in MISFIRE_POLICIES:
            raise ValueError(f"misfire_policy must be one of {', '.join(MISFIRE_POLICIES)}")
        return v

    @field_validator("cta_defaults")
    @classmethod
    def _cta(cls, v: dict[str, str]) -> dict[str, str]:
        unknown = set(v) - KNOWN_CTA_KEYS
        if unknown:
            raise ValueError(f"Unknown CTA keys: {', '.join(sorted(unknown))}")
        return {k: s.strip()[:300] for k, s in v.items() if s and s.strip()}


class BudgetIn(BaseModel):
    daily_budget_rub: Decimal = Field(ge=0, le=Decimal(1000000))
    monthly_budget_rub: Decimal = Field(ge=0, le=Decimal(10000000))
    max_cost_per_post_rub: Decimal = Field(ge=0, le=Decimal(100000))
    budget_warning_pct: int = Field(ge=1, le=100)


class NotificationPrefsIn(BaseModel):
    muted_kinds: list[str] = Field(default_factory=list)


@router.get("/ai-status", response_model=AIStatusResponse)
async def ai_status(workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member)):
    s = get_settings()
    image = get_image_provider()
    return AIStatusResponse(
        text_provider=get_text_provider().name, text_provider_is_fake=s.use_fake_ai_provider,
        image_provider=image.name, image_provider_status=(await image.status()).value,
        image_provider_is_fake=s.use_fake_image_provider, telegram_provider_is_fake=s.use_fake_telegram_provider,
    )


async def _settings_payload(db: AsyncSession, workspace_id: uuid.UUID) -> dict:
    s = get_settings()
    ws = await db.get(Workspace, workspace_id)
    row = await get_workspace_settings(db, workspace_id)
    budget = await CostService(db).budget_config(workspace_id)
    pricing = get_pricing_snapshot()
    image = get_image_provider()
    s3_host = urlparse(s.s3_endpoint).netloc if s.s3_endpoint else "AWS default"
    return {
        "general": {
            "workspace_name": ws.name, "timezone": row.timezone, "misfire_policy": row.misfire_policy,
            "misfire_grace_minutes": row.misfire_grace_minutes, "cta_defaults": json.loads(row.cta_defaults_json or "{}"),
            "cta_keys": sorted(KNOWN_CTA_KEYS - {"none"}),
        },
        "ai": {
            "text_provider": get_text_provider().name,
            "text_provider_is_fake": s.use_fake_ai_provider,
            "agent_base_url": mask_agent_url(s.timeweb_agent_base_url),
            "agent_api_key": mask_secret(s.timeweb_agent_api_key),
            "model": "GPT-6 Sol (selected in the Timeweb agent settings)",
            "pricing": {
                "text_input_rub_per_m": str(pricing.text_input_rub_per_m),
                "text_output_rub_per_m": str(pricing.text_output_rub_per_m),
                "image_input_rub_per_m": str(pricing.image_input_rub_per_m),
                "image_output_rub_per_m": str(pricing.image_output_rub_per_m),
            },
            "image_provider": image.name,
            "image_provider_status": (await image.status()).value,
            "image_provider_is_fake": s.use_fake_image_provider,
            "gateway_api_key": mask_secret(s.timeweb_ai_gateway_api_key),
            "gateway_image_model": s.timeweb_image_model or None,
        },
        "budget": {
            "daily_budget_rub": str(budget.daily_budget_rub), "monthly_budget_rub": str(budget.monthly_budget_rub),
            "max_cost_per_post_rub": str(budget.max_cost_per_post_rub),
            "budget_warning_pct": budget.budget_warning_pct or 80,
        },
        "telegram": {
            "api_id_configured": bool(s.telegram_api_id), "api_hash_configured": bool(s.telegram_api_hash),
            "session_encryption_configured": bool(s.telethon_session_encryption_key),
            "provider_is_fake": s.use_fake_telegram_provider,
        },
        "storage": {"endpoint_host": s3_host, "bucket": s.s3_bucket, "access_key": mask_secret(s.s3_access_key)},
        "security": {
            "session_max_age_hours": session_max_age() // 3600,
            "idle_timeout_hours": int(IDLE_TIMEOUT.total_seconds() // 3600),
            "secure_cookies": s.is_production,
            "environment": s.app_env,
        },
        "notifications": json.loads(row.notification_prefs_json or "{}"),
    }


@router.get("")
async def get_all_settings(workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member),
                           db: AsyncSession = Depends(get_db)):
    payload = await _settings_payload(db, workspace_id)
    await db.commit()
    return payload


@router.put("/general")
async def update_general(workspace_id: uuid.UUID, payload: GeneralIn,
                         member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    require_role(member.role, CAN_MANAGE_SETTINGS)
    try:
        validate_timezone(payload.timezone)
    except ScheduleValidationError as exc:
        from fastapi import HTTPException

        raise HTTPException(422, str(exc)) from exc
    ws = await db.get(Workspace, workspace_id)
    row = await get_workspace_settings(db, workspace_id)
    ws.name = payload.workspace_name
    row.timezone, row.misfire_policy = payload.timezone, payload.misfire_policy
    row.misfire_grace_minutes = payload.misfire_grace_minutes
    row.cta_defaults_json = json.dumps(payload.cta_defaults, ensure_ascii=False)
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="settings.general_updated",
                                  entity_type="workspace", entity_id=workspace_id, metadata=payload.model_dump())
    await db.commit()
    return await get_all_settings(workspace_id, member, db)


@router.put("/budget")
async def update_budget(workspace_id: uuid.UUID, payload: BudgetIn,
                        member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    require_role(member.role, CAN_MANAGE_SETTINGS)
    from app.api.v1.autopilot import _get_or_create

    config = await _get_or_create(db, workspace_id)
    before = {k: str(getattr(config, k)) for k in type(payload).model_fields}
    for field, value in payload.model_dump().items():
        setattr(config, field, value)
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="settings.budget_updated",
                                  entity_type="workspace", entity_id=workspace_id,
                                  metadata={"before": before, "after": payload.model_dump(mode="json")})
    await db.commit()
    return await get_all_settings(workspace_id, member, db)


@router.put("/notifications")
async def update_notifications(workspace_id: uuid.UUID, payload: NotificationPrefsIn,
                               member: WorkspaceMember = Depends(get_workspace_member),
                               user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_role(member.role, CAN_MANAGE_SETTINGS)
    row = await get_workspace_settings(db, workspace_id)
    row.notification_prefs_json = payload.model_dump_json()
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id,
                                  action="settings.notifications_updated", entity_type="workspace",
                                  entity_id=workspace_id, metadata=payload.model_dump())
    await db.commit()
    return await get_all_settings(workspace_id, member, db)
