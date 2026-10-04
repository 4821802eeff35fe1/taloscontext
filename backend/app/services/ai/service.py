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
from decimal import Decimal

import structlog
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AIOperation, AIRequestStatus
from app.schemas.generation import GenerationResult
from app.services.ai.base import ImageAIProvider, ImageProviderStatus, TextAIProvider
from app.services.costs.service import CostService

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
        last_error: Exception | None = None
        for attempt in range(2):  # 1 call + at most 1 automatic retry
            prompt = user_prompt if attempt == 0 else (
                user_prompt + "\n\nYour previous response was not valid JSON matching the "
                "required schema. Return ONLY the corrected JSON object."
            )
            completion = await self.text_provider.complete(
                system_prompt=system_prompt, user_prompt=prompt
            )
            try:
                parsed = _extract_json(completion.content)
                result = GenerationResult.model_validate(parsed)
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
                    error_message=str(exc),
                    raw_usage=completion.usage.raw,
                )
                log.warning("ai_json_parse_failed", attempt=attempt, error=str(exc))
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
                category=result.category,
            )
            return result, ai_request.total_cost_rub

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
        return result, ai_request
