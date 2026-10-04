"""Timeweb Cloud AI Agent integration.

Text: the agent exposes an OpenAI-compatible `/chat/completions` endpoint
(TIMEWEB_AGENT_BASE_URL). The agent's underlying model (GPT-6 Sol) is fixed by
the agent's own configuration in the Timeweb console — the `model` field in
the request body is accepted by the OpenAI-compatible shape but Timeweb's
docs do not guarantee it changes the actual model, so we send the field for
schema compliance only and never rely on it to pick a model.

Image: as of the current Timeweb documentation reviewed for this project, the
agent's OpenAI-compatible API does not expose a standard `/images/generations`
endpoint — image generation (GPT Image 2.5 Sunburst) is only described as
reachable through the hosted chat widget, not a documented program API. We do
NOT fabricate an endpoint. `TimewebGatewayImageProvider` below targets the
separate AI Gateway product (TIMEWEB_AI_GATEWAY_BASE_URL/TIMEWEB_IMAGE_MODEL);
it stays UNAVAILABLE until those env vars are populated with a confirmed,
documented Gateway image endpoint. See AI.md for the full rationale.
"""
from __future__ import annotations

import time

import httpx
import structlog

from app.core.config import get_settings
from app.services.ai.base import (
    ImageAIProvider,
    ImageGenerationResult,
    ImageProviderStatus,
    TextAIProvider,
    TextCompletionResult,
    TextCompletionUsage,
)

log = structlog.get_logger(__name__)


class TimewebAgentTextProvider(TextAIProvider):
    name = "timeweb-agent"

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.timeweb_agent_base_url.rstrip("/")
        self._api_key = settings.timeweb_agent_api_key

    async def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1200,
        temperature: float = 0.7,
    ) -> TextCompletionResult:
        if not self._api_key:
            raise RuntimeError("TIMEWEB_AGENT_API_KEY is not configured")

        payload = {
            "model": "agent-default",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}

        started = time.monotonic()
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions", json=payload, headers=headers
            )
        latency_ms = int((time.monotonic() - started) * 1000)

        if response.status_code >= 400:
            log.error("timeweb_agent_error", status=response.status_code)
            response.raise_for_status()

        data = response.json()
        choice = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        return TextCompletionResult(
            content=choice,
            usage=TextCompletionUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                raw=usage,
            ),
            provider=self.name,
            model=data.get("model", "gpt-6-sol"),
            latency_ms=latency_ms,
            provider_request_id=data.get("id"),
        )

    async def healthcheck(self) -> bool:
        if not self._api_key:
            return False
        try:
            await self.complete(system_prompt="ping", user_prompt="ping", max_tokens=1)
            return True
        except Exception:  # noqa: BLE001
            return False


class TimewebGatewayImageProvider(ImageAIProvider):
    """Stays UNAVAILABLE until a confirmed, documented Gateway image endpoint
    and model id are configured. Never guesses an endpoint path.
    """

    name = "timeweb-gateway-image"

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.timeweb_ai_gateway_base_url.rstrip("/")
        self._api_key = settings.timeweb_ai_gateway_api_key
        self._model = settings.timeweb_image_model

    def _configured(self) -> bool:
        return bool(self._base_url and self._api_key and self._model)

    async def status(self) -> ImageProviderStatus:
        # /models availability does not prove image generation support.
        # The documented Agent image feature is chat/widget only.
        return ImageProviderStatus.UNAVAILABLE

    async def generate(
        self,
        *,
        prompt: str,
        size: str = "1024x1024",
        reference_image_bytes: bytes | None = None,
    ) -> ImageGenerationResult:
        if not self._configured():
            raise RuntimeError(
                "Image provider unavailable: Timeweb AI Gateway image endpoint is not configured. "
                "No documented programmatic image API was available at implementation time."
            )
        raise NotImplementedError(
            "Wire the confirmed Gateway image endpoint here once TIMEWEB_AI_GATEWAY_* "
            "and TIMEWEB_IMAGE_MODEL are set and the endpoint shape is confirmed from docs."
        )

    def supports_reference_images(self) -> bool:
        return False

    def supports_sizes(self) -> list[str]:
        return ["1024x1024"]
