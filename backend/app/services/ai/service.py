"""AIService: the only place in the app allowed to call a TextAIProvider /
ImageAIProvider. Enforces "one main AI call per ordinary post" (ARCHITECTURE.md
§5) — callers ask for ONE GenerationResult; a second call only happens here,
automatically, and only to repair unparsable JSON, never to "improve" a valid
result.
"""
from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import TypeVar

import structlog
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cost import AIRequest
from app.models.enums import AIOperation, AIRequestStatus
from app.schemas.generation import GenerationResult
from app.services.ai.base import ImageAIProvider, ImageProviderStatus, TextAIProvider
from app.services.costs.service import CostService

T = TypeVar("T", bound=BaseModel)

log = structlog.get_logger(__name__)

SYSTEM_PROMPT_TEMPLATE = """You are the content engine for a Telegram channel network.
Return ONLY a single JSON object matching this exact shape, no prose, no markdown fences:

{{
  "schema_version": 1,
  "topic": string,
  "category": string,
  "angle": string,
  "title": string,
  "telegram_html": string,  // Telegram-safe HTML: only <b> <i> <u> <s> <a> <code> <pre> <blockquote>
  "plain_text": string,
  "cta_key": one of ["hr","affiliate","ceo","website","email","none"],
  "image_prompt": string,
  "tags": [string],
  "sources": [string],
  "duplicate_fingerprint": string, // short stable hash-like token summarizing the core claim
  "requires_review": boolean,
  "risk_flags": [string]
}}

Tone and context:
{tone_context}

Knowledge the post must respect (facts, allowed/forbidden claims):
{knowledge_context}

Topics already covered recently — do not repeat the same angle:
{recent_topics}
"""


class AIParseError(Exception):
    pass


class AIProviderError(Exception):
    """The provider call itself failed (network, auth, 5xx)."""


def _extract_json(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise AIParseError("No JSON object found in model output")
    return json.loads(match.group(0))


class AIService:
    def __init__(
        self,
        session: AsyncSession,
        text_provider: TextAIProvider,
        image_provider: ImageAIProvider,
    ):
        self.session = session
        self.text_provider = text_provider
        self.image_provider = image_provider
        self.cost_service = CostService(session)
        self.last_request: AIRequest | None = None

    async def generate_post(
        self,
        *,
        workspace_id: uuid.UUID,
        content_item_id: uuid.UUID | None,
        tone_context: str,
        knowledge_context: str,
        recent_topics: str,
        user_instruction: str,
        operation: AIOperation = AIOperation.GENERATE_POST,
    ) -> tuple[GenerationResult, Decimal]:
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            tone_context=tone_context or "Neutral, professional, concise.",
            knowledge_context=knowledge_context or "None provided.",
            recent_topics=recent_topics or "None.",
        )

        result, cost = await self._complete_with_one_retry(
            workspace_id=workspace_id,
            content_item_id=content_item_id,
            system_prompt=system_prompt,
            user_prompt=user_instruction,
            operation=operation,
        )
        return result, cost

    async def _complete_with_one_retry(
        self,
        *,
        workspace_id: uuid.UUID,
        content_item_id: uuid.UUID | None,
        system_prompt: str,
        user_prompt: str,
        operation: AIOperation,
    ) -> tuple[GenerationResult, Decimal]:
        result, ai_request = await self.complete_json(
            schema=GenerationResult,
            workspace_id=workspace_id,
            content_item_id=content_item_id,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            operation=operation,
            category_of=lambda r: r.category,
        )
        return result, ai_request.total_cost_rub

    async def complete_json(
        self,
        *,
        schema: type[T],
        workspace_id: uuid.UUID,
        content_item_id: uuid.UUID | None,
        system_prompt: str,
        user_prompt: str,
        operation: AIOperation,
        max_tokens: int = 1200,
        category_of: Callable[[T], str] | None = None,
    ) -> tuple[T, AIRequest]:
        """One provider call validated against `schema`; at most one automatic
        retry, only when the output can't be parsed. Every attempt — including
        failed ones — is recorded with its usage and cost."""
        await self.cost_service.assert_ai_allowed(
            workspace_id,
            self.cost_service.estimate_text_cost(len(system_prompt) + len(user_prompt), max_tokens),
        )
        last_error: Exception | None = None
        for attempt in range(2):  # 1 call + at most 1 automatic retry
            prompt = user_prompt if attempt == 0 else (
                user_prompt + "\n\nYour previous response was not valid JSON matching the "
                "required schema. Return ONLY the corrected JSON object."
            )
            try:
                completion = await self.text_provider.complete(
                    system_prompt=system_prompt, user_prompt=prompt, max_tokens=max_tokens
                )
            except Exception as exc:
                await self.cost_service.record_ai_request(
                    workspace_id=workspace_id, content_item_id=content_item_id,
                    provider=self.text_provider.name, model="", operation=operation,
                    prompt_tokens=0, completion_tokens=0, latency_ms=0, is_image=False,
                    status=AIRequestStatus.FAILED, error_message=f"{type(exc).__name__}: {exc}"[:2000],
                )
                raise AIProviderError(f"AI provider request failed: {type(exc).__name__}") from exc
            try:
                result = schema.model_validate(_extract_json(completion.content))
            except (AIParseError, json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                await self.cost_service.record_ai_request(
                    workspace_id=workspace_id,
                    content_item_id=content_item_id,
                    provider=completion.provider,
                    model=completion.model,
                    operation=operation,
                    prompt_tokens=completion.usage.prompt_tokens,
                    completion_tokens=completion.usage.completion_tokens,
                    latency_ms=completion.latency_ms,
                    is_image=False,
                    provider_request_id=completion.provider_request_id,
                    status=AIRequestStatus.RETRIED if attempt == 0 else AIRequestStatus.FAILED,
                    error_message=str(exc)[:2000],
                    raw_usage=completion.usage.raw,
                )
                log.warning("ai_json_parse_failed", attempt=attempt, error=str(exc)[:200])
                continue

            ai_request = await self.cost_service.record_ai_request(
                workspace_id=workspace_id,
                content_item_id=content_item_id,
                provider=completion.provider,
                model=completion.model,
                operation=operation,
                prompt_tokens=completion.usage.prompt_tokens,
                completion_tokens=completion.usage.completion_tokens,
                latency_ms=completion.latency_ms,
                is_image=False,
                provider_request_id=completion.provider_request_id,
                status=AIRequestStatus.SUCCESS,
                raw_usage=completion.usage.raw,
                category=category_of(result) if category_of else "",
            )
            self.last_request = ai_request
            await self.cost_service.check_budget_thresholds(workspace_id)
            return result, ai_request

        raise AIParseError(
            f"Model output could not be parsed as valid JSON after retry: {last_error}"
        )

    async def image_provider_status(self) -> ImageProviderStatus:
        return await self.image_provider.status()

    async def generate_image(
        self,
        *,
        workspace_id: uuid.UUID,
        content_item_id: uuid.UUID | None,
        prompt: str,
    ):
        status = await self.image_provider.status()
        await self.cost_service.assert_ai_allowed(workspace_id, Decimal(0))
        if status != ImageProviderStatus.AVAILABLE:
            raise RuntimeError(
                "Image provider is not available through the configured Timeweb API."
            )
        result = await self.image_provider.generate(prompt=prompt)
        ai_request = await self.cost_service.record_ai_request(
            workspace_id=workspace_id,
            content_item_id=content_item_id,
            provider=result.provider,
            model=result.model,
            operation=AIOperation.GENERATE_IMAGE,
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.output_tokens,
            latency_ms=result.latency_ms,
            is_image=True,
            raw_usage=result.usage.raw,
        )
        self.last_request = ai_request
        await self.cost_service.check_budget_thresholds(workspace_id)
        return result, ai_request
