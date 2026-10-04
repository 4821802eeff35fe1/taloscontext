from __future__ import annotations

import json
import random
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.enums import AutopilotMode
from app.models.scheduling import AutopilotConfig, Schedule, ScheduleRule
from app.services.content.service import ContentService
from app.services.costs.service import BudgetExceededError, CostService
from app.services.scheduling.service import ScheduleService


class AutopilotService:
    """Daily planner: builds the content mix, enforces the budget guard before
    issuing any AI call, and routes the resulting ContentItem according to the
    workspace's mode (MANUAL never auto-creates; APPROVAL stops at the queue;
    AUTOPILOT also schedules/publishes). Publishing itself is never blocked by
    AI budget — only new generation is (product brief §28).
    """

    def __init__(self, session: AsyncSession, content_service: ContentService):
        self.session = session
        self.content_service = content_service
        self.cost_service = CostService(session)
        self.schedule_service = ScheduleService()

    def pick_category(self, config: AutopilotConfig) -> str:
        mix: dict[str, float] = json.loads(config.category_mix_json or "{}")
        if not mix:
            return "educational"
        categories = list(mix.keys())
        weights = list(mix.values())
        return random.choices(categories, weights=weights, k=1)[0]

    async def plan_one(self, *, workspace_id: uuid.UUID, config: AutopilotConfig) -> ContentItem | None:
        if config.mode == AutopilotMode.MANUAL:
            return None

        estimated_cost = config.max_cost_per_post_rub
        try:
            await self.cost_service.assert_budget_available(workspace_id, config, estimated_cost)
        except BudgetExceededError:
            return None

        category = self.pick_category(config)
        instruction = f"Write a Telegram post. Category: {category}. Keep it concise and on-brand."

        item = await self.content_service.generate(
            workspace_id=workspace_id,
            user_id=None,
            user_instruction=instruction,
            channel_set_id=config.channel_set_id,
            tone_profile_id=config.tone_profile_id,
        )

        if item.requires_review or (item.duplicate_score or 0) >= config.duplicate_block_threshold:
            await self.content_service.submit_for_approval(item)
            return item

        if category == "news" and config.require_sources_for_news:
            sources = json.loads(item.sources_json or "[]")
            if not sources:
                await self.content_service.submit_for_approval(item)
                return item

        if config.mode == AutopilotMode.APPROVAL:
            await self.content_service.submit_for_approval(item)
            return item

        # AUTOPILOT: auto-approve and schedule the next available slot.
        await self.content_service.submit_for_approval(item)
        await self.content_service.approve(item)

        schedule = await self.session.get(Schedule, config.schedule_id) if config.schedule_id else None
        if schedule:
            rules_result = await self.session.execute(
                select(ScheduleRule).where(ScheduleRule.schedule_id == schedule.id)
            )
            rules = rules_result.scalars().all()
            slots = self.schedule_service.next_slot(schedule, rules, after=datetime.now(UTC))
            if slots:
                await self.content_service.schedule(item, scheduled_at=slots[0])

        return item
