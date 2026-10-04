from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_workspace_member
from app.models.identity import WorkspaceMember
from app.models.scheduling import AutopilotConfig
from app.services.analytics.service import AnalyticsService
from app.services.costs.service import CostService

router = APIRouter(prefix="/workspaces/{workspace_id}/analytics", tags=["analytics"])


class CostDashboardResponse(BaseModel):
    today_rub: Decimal
    month_rub: Decimal
    month_budget_rub: Decimal
    forecast_month_end_rub: Decimal


@router.get("/costs", response_model=CostDashboardResponse)
async def cost_dashboard(
    workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db)
):
    service = CostService(db)
    today = await service.today_spend(workspace_id)
    month = await service.month_spend(workspace_id)
    forecast = await service.forecast_month_end(workspace_id)

    from sqlalchemy import select

    config_result = await db.execute(select(AutopilotConfig).where(AutopilotConfig.workspace_id == workspace_id))
    config = config_result.scalar_one_or_none()
    month_budget = config.monthly_budget_rub if config else Decimal(1500)

    return CostDashboardResponse(
        today_rub=today, month_rub=month, month_budget_rub=month_budget, forecast_month_end_rub=forecast
    )


@router.get("/content/{content_id}")
async def content_item_analytics(
    workspace_id: uuid.UUID, content_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException, status

    from app.models.content import ContentItem

    item = await db.get(ContentItem, content_id)
    if not item or item.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content item not found")
    service = AnalyticsService(db)
    return await service.content_item_totals(content_id)
