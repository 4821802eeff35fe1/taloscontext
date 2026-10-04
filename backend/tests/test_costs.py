from decimal import Decimal

import pytest

from app.models.enums import AIOperation
from app.models.scheduling import AutopilotConfig
from app.services.costs.service import BudgetExceededError, CostService, compute_cost


def test_compute_cost_matches_formula():
    input_cost, output_cost, total = compute_cost(
        prompt_tokens=1000, completion_tokens=500,
        input_rate=Decimal(270), output_rate=Decimal(1350),
    )
    assert input_cost == (Decimal(1000) / Decimal(1_000_000)) * Decimal(270)
    assert output_cost == (Decimal(500) / Decimal(1_000_000)) * Decimal(1350)
    assert total == input_cost + output_cost


@pytest.mark.asyncio
async def test_record_ai_request_persists_cost_event(db_session, workspace):
    workspace_id = workspace.id
    service = CostService(db_session)
    request = await service.record_ai_request(
        workspace_id=workspace_id, content_item_id=None, provider="fake-ai", model="fake-gpt",
        operation=AIOperation.GENERATE_POST, prompt_tokens=1_000_000, completion_tokens=1_000_000,
        latency_ms=10, is_image=False,
    )
    assert request.total_cost_rub == Decimal(270) + Decimal(1350)

    today_spend = await service.today_spend(workspace_id)
    assert today_spend == request.total_cost_rub


@pytest.mark.asyncio
async def test_budget_guard_blocks_when_daily_cap_would_be_exceeded(db_session, workspace):
    workspace_id = workspace.id
    service = CostService(db_session)
    config = AutopilotConfig(
        workspace_id=workspace_id, daily_budget_rub=Decimal(10),
        monthly_budget_rub=Decimal(100), max_cost_per_post_rub=Decimal(5),
    )

    await service.assert_budget_available(workspace_id, config, Decimal(5))

    with pytest.raises(BudgetExceededError) as exc_info:
        await service.assert_budget_available(workspace_id, config, Decimal(6))
    assert exc_info.value.kind == "per_post"


@pytest.mark.asyncio
async def test_budget_guard_blocks_on_monthly_cap(db_session, workspace):
    workspace_id = workspace.id
    service = CostService(db_session)
    config = AutopilotConfig(
        workspace_id=workspace_id, daily_budget_rub=Decimal(1000),
        monthly_budget_rub=Decimal(10), max_cost_per_post_rub=Decimal(1000),
    )
    await service.record_ai_request(
        workspace_id=workspace_id, content_item_id=None, provider="fake", model="fake",
        operation=AIOperation.GENERATE_POST, prompt_tokens=1_000_000, completion_tokens=0,
        latency_ms=1, is_image=False,
    )
    # text input rate defaults to 270 RUB/million -> spent so far == 270, way over monthly=10
    with pytest.raises(BudgetExceededError) as exc_info:
        await service.assert_budget_available(workspace_id, config, Decimal(1))
    assert exc_info.value.kind == "monthly"
