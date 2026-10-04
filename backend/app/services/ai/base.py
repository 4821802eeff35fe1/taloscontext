"""Provider abstractions. The rest of the app depends only on these interfaces —
never on a concrete Timeweb/OpenAI/fake class — so swapping or adding a provider
never touches business logic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class ImageProviderStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


@dataclass
class TextCompletionUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    raw: dict = field(default_factory=dict)


@dataclass
class TextCompletionResult:
    content: str
    usage: TextCompletionUsage
    provider: str
    model: str
    latency_ms: int
    provider_request_id: str | None = None


@dataclass
class ImageGenerationUsage:
    prompt_tokens: int = 0
    output_tokens: int = 0
    raw: dict = field(default_factory=dict)


@dataclass
class ImageGenerationResult:
    image_bytes: bytes
    mime_type: str
    width: int | None
    height: int | None
    usage: ImageGenerationUsage
    provider: str
    model: str
    latency_ms: int


@dataclass
class WebSearchResult:
    title: str
    url: str
    snippet: str
    published_at: str | None = None


class TextAIProvider(ABC):
    name: str = "text-provider"

    @abstractmethod
    async def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1200,
        temperature: float = 0.7,
    ) -> TextCompletionResult: ...

    @abstractmethod
    async def healthcheck(self) -> bool: ...


class ImageAIProvider(ABC):
    name: str = "image-provider"

    @abstractmethod
    async def status(self) -> ImageProviderStatus: ...

    @abstractmethod
    async def generate(
        self,
        *,
        prompt: str,
        size: str = "1024x1024",
        reference_image_bytes: bytes | None = None,
    ) -> ImageGenerationResult: ...

    @abstractmethod
    def supports_reference_images(self) -> bool: ...

    @abstractmethod
    def supports_sizes(self) -> list[str]: ...


class SearchProvider(ABC):
    name: str = "search-provider"

    @abstractmethod
    async def search(self, query: str, *, limit: int = 5) -> list[WebSearchResult]: ...
