"""AI_GENERATE_POST job: the one AI call that turns a request into a draft."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.enums import ContentStatus
from app.models.ops import Job
from app.services.ai.factory import get_image_provider, get_text_provider
from app.services.ai.service import AIParseError, AIProviderError, AIService
from app.services.audit.service import AuditService
from app.services.content.context import PromptContextBuilder
from app.services.content.service import ContentService
from app.services.costs.service import BudgetExceededError
from app.services.jobs.service import Emit, JobFailed
from app.services.notifications.service import NotificationService


async def run_generation(session: AsyncSession, job: Job, payload: dict[str, Any], emit: Emit) -> dict[str, Any]:
    item = await session.get(ContentItem, uuid.UUID(payload["content_id"]))
    if item is None or item.workspace_id != job.workspace_id:
        raise JobFailed("CONTENT_NOT_FOUND", "Content item no longer exists")
    if item.status == ContentStatus.FAILED:
        item.status = ContentStatus.GENERATING  # manual retry of a failed generation
    if item.status != ContentStatus.GENERATING:
        return {"note": f"content is {item.status.value}; nothing to generate"}

    instruction = (payload.get("instruction") or "").strip()
    context = await PromptContextBuilder(session).build(item, instruction)
    if not instruction and item.topic:
        instruction = f"Write a Telegram post about: {item.topic}"

    ai_service = AIService(session, get_text_provider(), get_image_provider())
    content_service = ContentService(session, ai_service)
    notifier = NotificationService(session)
    try:
        await content_service.complete_generation(
            item,
            user_id=job.created_by_user_id,
            user_instruction=instruction,
            tone_context=context.tone_context,
            knowledge_context=context.knowledge_context,
            extra_context=context.series_context,
        )
    except BudgetExceededError as exc:
        item.status = ContentStatus.FAILED
        raise JobFailed("BUDGET_EXCEEDED", str(exc)) from exc
    except (AIParseError, AIProviderError) as exc:
        item.status = ContentStatus.FAILED
        await notifier.notify(
            workspace_id=item.workspace_id, kind="ai.failed",
            message=f"AI generation failed: {exc}", metadata={"content_id": str(item.id), "job_id": str(job.id)},
            emit=emit,
        )
        code = "AI_INVALID_RESPONSE" if isinstance(exc, AIParseError) else "AI_PROVIDER_ERROR"
        raise JobFailed(code, str(exc)) from exc

    if item.source_item_id:
        from app.models.enums import IdeaStatus
        from app.models.sources import SourceItem

        idea = await session.get(SourceItem, item.source_item_id)
        if idea is not None:
            idea.status = IdeaStatus.USED

    await AuditService(session).record(
        workspace_id=item.workspace_id, actor_user_id=job.created_by_user_id, action="content.generated",
        entity_type="content", entity_id=item.id,
        metadata={"tone_source": context.tone_source, "knowledge_docs": len(context.used_knowledge_ids)},
    )
    cost = ai_service.last_request.total_cost_rub if ai_service.last_request else 0
    emit("content.generated", {"content_id": str(item.id), "status": item.status.value, "cost_rub": str(cost)})
    return {"content_id": str(item.id), "cost_rub": str(cost), "tone_source": context.tone_source}
