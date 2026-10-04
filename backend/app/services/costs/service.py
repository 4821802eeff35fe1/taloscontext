from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.cost import AIRequest, CostEvent
from app.models.enums import AIOperation, AIRequestStatus
from app.models.scheduling import AutopilotConfig


class BudgetExceededError(Exception):
    def __init__(self, message: str, kind: str):
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class PricingSnapshot:
    text_input_rub_per_m: Decimal
    text_output_rub_per_m: Decimal
    image_input_rub_per_m: Decimal
    image_output_rub_per_m: Decimal


def get_pricing_snapshot() -> PricingSnapshot:
    s = get_settings()
    return PricingSnapshot(
        text_input_rub_per_m=s.timeweb_text_input_rub_per_m,
        text_output_rub_per_m=s.timeweb_text_output_rub_per_m,
        image_input_rub_per_m=s.timeweb_image_input_rub_per_m,
        image_output_rub_per_m=s.timeweb_image_output_rub_per_m,
    )


def compute_cost(
    prompt_tokens: int, completion_tokens: int, input_rate: Decimal, output_rate: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    million = Decimal(1_000_000)
    input_cost = (Decimal(prompt_tokens) / million) * input_rate
    output_cost = (Decimal(completion_tokens) / million) * output_rate
    return input_cost, output_cost, input_cost + output_cost


class CostService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_ai_request(
        self,
        *,
        workspace_id: uuid.UUID,
        content_item_id: uuid.UUID | None,
        provider: str,
        model: str,
        operation: AIOperation,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        is_image: bool,
        provider_request_id: str | None = None,
        status: AIRequestStatus = AIRequestStatus.SUCCESS,
        error_message: str | None = None,
        raw_usage: dict | None = None,
        channel_id: uuid.UUID | None = None,
        channel_set_id: uuid.UUID | None = None,
        category: str = "",
    ) -> AIRequest:
        pricing = get_pricing_snapshot()
        input_rate = pricing.image_input_rub_per_m if is_image else pricing.text_input_rub_per_m
        output_rate = pricing.image_output_rub_per_m if is_image else pricing.text_output_rub_per_m
        input_cost, output_cost, total_cost = compute_cost(
            prompt_tokens, completion_tokens, input_rate, output_rate
        )

        ai_request = AIRequest(
            workspace_id=workspace_id,
            content_item_id=content_item_id,
            provider=provider,
            model=model,
            operation=operation,
            provider_request_id=provider_request_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            input_rate_rub_per_m=input_rate,
            output_rate_rub_per_m=output_rate,
            input_cost_rub=input_cost,
            output_cost_rub=output_cost,
            total_cost_rub=total_cost,
            latency_ms=latency_ms,
            status=status,
            raw_usage_json=_dumps(raw_usage or {}),
            error_message=error_message,
        )
        self.session.add(ai_request)
        await self.session.flush()

        if status == AIRequestStatus.SUCCESS and total_cost > 0:
            self.session.add(
                CostEvent(
                    workspace_id=workspace_id,
                    ai_request_id=ai_request.id,
                    content_item_id=content_item_id,
                    channel_id=channel_id,
                    channel_set_id=channel_set_id,
                    category=category,
                    provider=provider,
                    operation=operation,
                    amount_rub=total_cost,
                )
            )
            await self.session.flush()

        return ai_request

    async def spend_since(self, workspace_id: uuid.UUID, since: datetime) -> Decimal:
        result = await self.session.execute(
            select(func.coalesce(func.sum(CostEvent.amount_rub), 0)).where(
                CostEvent.workspace_id == workspace_id, CostEvent.created_at >= since
            )
        )
        return Decimal(result.scalar_one())

    async def today_spend(self, workspace_id: uuid.UUID) -> Decimal:
        now = datetime.now(UTC)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return await self.spend_since(workspace_id, start)

    async def month_spend(self, workspace_id: uuid.UUID) -> Decimal:
        now = datetime.now(UTC)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return await self.spend_since(workspace_id, start)

    async def assert_budget_available(
        self, workspace_id: uuid.UUID, config: AutopilotConfig, estimated_cost: Decimal
    ) -> None:
        today = await self.today_spend(workspace_id)
        if today + estimated_cost > config.daily_budget_rub:
            raise BudgetExceededError(
                f"Daily AI budget would be exceeded ({today} + {estimated_cost} > "
                f"{config.daily_budget_rub} RUB). Autopilot generation is paused until tomorrow.",
                kind="daily",
            )
        month = await self.month_spend(workspace_id)
        if month + estimated_cost > config.monthly_budget_rub:
            raise BudgetExceededError(
                f"Monthly AI budget would be exceeded ({month} + {estimated_cost} > "
                f"{config.monthly_budget_rub} RUB). Autopilot generation is paused until next month.",
                kind="monthly",
            )
        if estimated_cost > config.max_cost_per_post_rub:
            raise BudgetExceededError(
                f"Estimated post cost {estimated_cost} RUB exceeds max_cost_per_post_rub "
                f"({config.max_cost_per_post_rub} RUB).",
                kind="per_post",
            )

    async def forecast_month_end(self, workspace_id: uuid.UUID) -> Decimal:
        now = datetime.now(UTC)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        days_elapsed = max(1, (now - start).days + 1)
        next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        days_in_month = (next_month - start).days
        spent = await self.month_spend(workspace_id)
        daily_rate = spent / Decimal(days_elapsed)
        return (daily_rate * Decimal(days_in_month)).quantize(Decimal("0.01"))


def _dumps(data: dict) -> str:
    import json

    return json.dumps(data, ensure_ascii=False, default=str)
