"""Deterministic fake providers for local dev / tests — never cost real money,
never hit the network. UI should show a visible "fake provider" indicator
whenever these are active (see GET /api/v1/settings/ai-status).
"""
from __future__ import annotations

import hashlib
import json

from app.services.ai.base import (
    ImageAIProvider,
    ImageGenerationResult,
    ImageGenerationUsage,
    ImageProviderStatus,
    SearchProvider,
    TextAIProvider,
    TextCompletionResult,
    TextCompletionUsage,
    WebSearchResult,
)

_FAKE_PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000c4944415408d763f8ffff3f0005fe02fea739666d0000000049454e44ae426082"
)


class FakeAIProvider(TextAIProvider):
    name = "fake-ai"

    async def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1200,
        temperature: float = 0.7,
    ) -> TextCompletionResult:
        fingerprint = hashlib.sha1(user_prompt.encode("utf-8")).hexdigest()[:16]
        if "You edit Telegram channel posts" in system_prompt:
            return self._edit(user_prompt, system_prompt, fingerprint)
        body = {
            "schema_version": 1,
            "topic": "Fake generated topic",
            "category": "educational",
            "angle": "practical-tips",
            "title": "5 способов улучшить ваш CTR",
            "telegram_html": "<b>5 способов улучшить ваш CTR</b>\n\nКороткий практичный пост "
            "с конкретными советами по улучшению показателей кампании.",
            "plain_text": "5 способов улучшить ваш CTR\n\nКороткий практичный пост с конкретными "
            "советами по улучшению показателей кампании.",
            "cta_key": "website",
            "image_prompt": "Minimal flat illustration of a growth chart, blue tones",
            "tags": ["media-buying", "ctr", "tips"],
            "sources": [],
            "duplicate_fingerprint": fingerprint,
            "requires_review": False,
            "risk_flags": [],
        }
        content = json.dumps(body, ensure_ascii=False)
        prompt_tokens = max(1, len(system_prompt + user_prompt) // 4)
        completion_tokens = max(1, len(content) // 4)
        return TextCompletionResult(
            content=content,
            usage=TextCompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                raw={"fake": True},
            ),
            provider=self.name,
            model="fake-gpt",
            latency_ms=5,
            provider_request_id=f"fake-{fingerprint}",
        )

    async def healthcheck(self) -> bool:
        return True

    def _edit(self, user_prompt: str, system_prompt: str, fingerprint: str) -> TextCompletionResult:
        """Deterministic, recognisable edits so tests can assert on the outcome."""
        task = user_prompt.split("\n", 1)[0]
        current = user_prompt.split("Current post (Telegram HTML):\n", 1)[-1]
        title_line = next((ln for ln in user_prompt.splitlines() if ln.startswith("Current title: ")), "")
        title = title_line.removeprefix("Current title: ")
        html, cta = current, None
        if "Shorten" in task:
            html = current[: max(20, len(current) // 2)].rstrip() + "…"
        elif "Expand" in task:
            html = current + "\n\nДополнительная деталь: проверяйте гипотезы на небольшом бюджете."
        elif "headline" in task:
            title = f"Лучше: {title}" if title else "Новый заголовок"
        elif "call-to-action" in task:
            cta = "website"
        elif "ONLY the selected fragment" in task:
            selected = user_prompt.split("Selected fragment:\n«", 1)[-1].split("»", 1)[0]
            html = current.replace(selected, f"<i>{selected} (переписано)</i>", 1) if selected else current
        else:
            html = current + "\n\n<i>(отредактировано)</i>"
        content = json.dumps({"title": title, "telegram_html": html, "cta_key": cta, "notes": task[:80]},
                             ensure_ascii=False)
        prompt_tokens = max(1, len(system_prompt + user_prompt) // 4)
        completion_tokens = max(1, len(content) // 4)
        return TextCompletionResult(
            content=content,
            usage=TextCompletionUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                                      total_tokens=prompt_tokens + completion_tokens, raw={"fake": True}),
            provider=self.name, model="fake-gpt", latency_ms=5, provider_request_id=f"fake-edit-{fingerprint}",
        )


class FakeImageProvider(ImageAIProvider):
    name = "fake-image"

    async def status(self) -> ImageProviderStatus:
        return ImageProviderStatus.AVAILABLE

    async def generate(
        self,
        *,
        prompt: str,
        size: str = "1024x1024",
        reference_image_bytes: bytes | None = None,
    ) -> ImageGenerationResult:
        return ImageGenerationResult(
            image_bytes=_FAKE_PNG_1x1,
            mime_type="image/png",
            width=1,
            height=1,
            usage=ImageGenerationUsage(prompt_tokens=20, output_tokens=0, raw={"fake": True}),
            provider=self.name,
            model="fake-image-model",
            latency_ms=5,
        )

    def supports_reference_images(self) -> bool:
        return False

    def supports_sizes(self) -> list[str]:
        return ["1024x1024", "512x512"]


class FakeSearchProvider(SearchProvider):
    name = "fake-search"

    async def search(self, query: str, *, limit: int = 5) -> list[WebSearchResult]:
        return [
            WebSearchResult(
                title=f"Fake result for '{query}'",
                url="https://example.com/fake-article",
                snippet="This is a deterministic fake search result used in development/tests.",
                published_at=None,
            )
        ][:limit]
