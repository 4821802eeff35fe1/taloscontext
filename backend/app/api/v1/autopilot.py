from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_workspace_member
from app.core.rbac import CAN_MANAGE_SETTINGS, require_role
from app.models.enums import AutopilotMode
from app.models.identity import WorkspaceMember
from app.models.scheduling import AutopilotConfig

router = APIRouter(prefix="/workspaces/{workspace_id}/autopilot", tags=["autopilot"])


class AutopilotResponse(BaseModel):
    mode: str
    channel_set_id: uuid.UUID | None
    schedule_id: uuid.UUID | None
    posts_per_day: int
    daily_budget_rub: Decimal
    monthly_budget_rub: Decimal
    max_cost_per_post_rub: Decimal
    generate_image: bool


class AutopilotUpdateRequest(BaseModel):
    mode: str | None = None
    channel_set_id: uuid.UUID | None = None
    schedule_id: uuid.UUID | None = None
    posts_per_day: int | None = None
    daily_budget_rub: Decimal | None = None
    monthly_budget_rub: Decimal | None = None
    max_cost_per_post_rub: Decimal | None = None
    generate_image: bool | None = None


def _to_response(c: AutopilotConfig) -> AutopilotResponse:
    return AutopilotResponse(
        mode=c.mode.value, channel_set_id=c.channel_set_id, schedule_id=c.schedule_id,
        posts_per_day=c.posts_per_day, daily_budget_rub=c.daily_budget_rub,
        monthly_budget_rub=c.monthly_budget_rub, max_cost_per_post_rub=c.max_cost_per_post_rub,
        generate_image=c.generate_image,
    )


async def _get_or_create(db: AsyncSession, workspace_id: uuid.UUID) -> AutopilotConfig:
    result = await db.execute(select(AutopilotConfig).where(AutopilotConfig.workspace_id == workspace_id))
    config = result.scalar_one_or_none()
    if config is None:
        config = AutopilotConfig(workspace_id=workspace_id)
        db.add(config)
        await db.flush()
    return config


@router.get("", response_model=AutopilotResponse)
async def get_autopilot(
    workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db)
):
    config = await _get_or_create(db, workspace_id)
    await db.commit()
    return _to_response(config)


@router.patch("", response_model=AutopilotResponse)
async def update_autopilot(
    workspace_id: uuid.UUID, payload: AutopilotUpdateRequest,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_MANAGE_SETTINGS)
    config = await _get_or_create(db, workspace_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("channel_set_id"):
        from app.models.telegram import ChannelSet

        cs = await db.get(ChannelSet, updates["channel_set_id"])
        if cs is None or cs.workspace_id != workspace_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel set not found")
    if updates.get("schedule_id"):
        from app.models.scheduling import Schedule

        sc = await db.get(Schedule, updates["schedule_id"])
        if sc is None or sc.workspace_id != workspace_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")
    from app.services.audit.service import AuditService

    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=member.user_id, action="autopilot.updated",
                                  entity_type="workspace", entity_id=workspace_id,
                                  metadata={k: str(v) for k, v in updates.items()})
    if "mode" in updates:
        updates["mode"] = AutopilotMode(updates["mode"])
    for field, value in updates.items():
        setattr(config, field, value)
    await db.commit()
    return _to_response(config)
