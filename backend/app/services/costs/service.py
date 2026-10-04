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
    def __init__(self, message: str, kind: str, spent: Decimal | None = None, limit: Decimal | None = None):
        super().__init__(message)
        self.kind = kind
        self.spent = str(spent) if spent is not None else None
        self.limit = str(limit) if limit is not None else None


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

        if total_cost > 0:
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
                kind="daily", spent=today, limit=Decimal(config.daily_budget_rub),
            )
        month = await self.month_spend(workspace_id)
        if month + estimated_cost > config.monthly_budget_rub:
            raise BudgetExceededError(
                f"Monthly AI budget would be exceeded ({month} + {estimated_cost} > "
                f"{config.monthly_budget_rub} RUB). Autopilot generation is paused until next month.",
                kind="monthly", spent=month, limit=Decimal(config.monthly_budget_rub),
            )
        if estimated_cost > config.max_cost_per_post_rub:
            raise BudgetExceededError(
                f"Estimated post cost {estimated_cost} RUB exceeds max_cost_per_post_rub "
                f"({config.max_cost_per_post_rub} RUB).",
                kind="per_post", spent=estimated_cost, limit=Decimal(config.max_cost_per_post_rub),
            )

    async def budget_config(self, workspace_id: uuid.UUID) -> AutopilotConfig:
        """Budget limits live on the workspace's AutopilotConfig; unsaved -> defaults."""
        result = await self.session.execute(
            select(AutopilotConfig).where(AutopilotConfig.workspace_id == workspace_id)
        )
        config = result.scalar_one_or_none()
        if config is None:
            config = AutopilotConfig(
                workspace_id=workspace_id, daily_budget_rub=Decimal(50), monthly_budget_rub=Decimal(1500),
                max_cost_per_post_rub=Decimal(15), budget_warning_pct=80,
            )
        return config

    def estimate_text_cost(self, prompt_chars: int, max_output_tokens: int) -> Decimal:
        """Upper-bound estimate (~4 chars/token, full output budget used)."""
        pricing = get_pricing_snapshot()
        _, _, total = compute_cost(
            prompt_chars // 4 + 1, max_output_tokens,
            pricing.text_input_rub_per_m, pricing.text_output_rub_per_m,
        )
        return total.quantize(Decimal("0.0001"))

    async def assert_ai_allowed(self, workspace_id: uuid.UUID, estimated_cost: Decimal) -> None:
        """Daily/monthly caps apply to every AI operation, manual or automatic.
        Publishing already-approved content is never gated by this."""
        # Hold the workspace row through the AI call and cost commit so concurrent
        # workers cannot all pass the same budget check before any spend is recorded.
        from app.models.identity import Workspace

        await self.session.get(Workspace, workspace_id, with_for_update=True)
        config = await self.budget_config(workspace_id)
        today = await self.today_spend(workspace_id)
        if today + estimated_cost > Decimal(config.daily_budget_rub):
            raise BudgetExceededError(
                f"AI daily budget reached ({today:.2f} of {Decimal(config.daily_budget_rub):.2f} ₽). "
                "AI generation resumes tomorrow, or raise the limit in Settings → Budget.",
                kind="daily", spent=today, limit=Decimal(config.daily_budget_rub),
            )
        month = await self.month_spend(workspace_id)
        if month + estimated_cost > Decimal(config.monthly_budget_rub):
            raise BudgetExceededError(
                f"AI monthly budget reached ({month:.2f} of {Decimal(config.monthly_budget_rub):.2f} ₽). "
                "Raise the limit in Settings → Budget to continue.",
                kind="monthly", spent=month, limit=Decimal(config.monthly_budget_rub),
            )

        if estimated_cost > Decimal(config.max_cost_per_post_rub):
            raise BudgetExceededError("Estimated AI cost exceeds the maximum per post.", kind="post",
                                     spent=estimated_cost, limit=Decimal(config.max_cost_per_post_rub))

    async def check_budget_thresholds(self, workspace_id: uuid.UUID) -> None:
        """Raises warning/exceeded notifications once per period when a threshold is crossed."""
        from app.services.notifications.service import NotificationService
        from app.services.realtime.events import publish_event

        config = await self.budget_config(workspace_id)
        warn_pct = Decimal(config.budget_warning_pct or 80) / Decimal(100)
        now = datetime.now(UTC)
        checks = (
            ("daily", await self.today_spend(workspace_id), Decimal(config.daily_budget_rub), now.date().isoformat()),
            ("monthly", await self.month_spend(workspace_id), Decimal(config.monthly_budget_rub), now.strftime("%Y-%m")),
        )
        notifier = NotificationService(self.session)
        for period, spent, limit, period_key in checks:
            if limit <= 0:
                continue
            if spent >= limit:
                kind, event = "budget.exceeded", "budget.exceeded"
                msg = f"AI {period} budget reached: {spent:.2f} of {limit:.2f} ₽. Autopilot generation is paused."
            elif spent >= limit * warn_pct:
                kind, event = "budget.warning", "budget.warning"
                msg = f"AI {period} spend at {int(spent / limit * 100)}%: {spent:.2f} of {limit:.2f} ₽."
            else:
                continue
            created = await notifier.notify(
                workspace_id=workspace_id, kind=kind, message=msg,
                metadata={"period": period, "spent": str(spent), "limit": str(limit)},
                dedupe_key=f"{kind}:{period}:{period_key}", dedupe_window=timedelta(days=31),
            )
            if created:
                await publish_event(workspace_id, event, {"period": period, "spent": str(spent), "limit": str(limit)})

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
