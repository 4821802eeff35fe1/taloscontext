from functools import lru_cache

from app.core.config import get_settings
from app.services.ai.base import ImageAIProvider, SearchProvider, TextAIProvider
from app.services.ai.fake_provider import FakeAIProvider, FakeImageProvider, FakeSearchProvider
from app.services.ai.timeweb_provider import TimewebAgentTextProvider, TimewebGatewayImageProvider


@lru_cache
def get_text_provider() -> TextAIProvider:
    settings = get_settings()
    if settings.use_fake_ai_provider:
        return FakeAIProvider()
    return TimewebAgentTextProvider()


@lru_cache
def get_image_provider() -> ImageAIProvider:
    settings = get_settings()
    if settings.use_fake_image_provider:
        return FakeImageProvider()
    return TimewebGatewayImageProvider()


@lru_cache
def get_search_provider() -> SearchProvider:
    return FakeSearchProvider()
