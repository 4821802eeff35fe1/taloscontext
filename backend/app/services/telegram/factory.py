from app.core.config import get_settings
from app.services.telegram.base import TelegramProvider
from app.services.telegram.fake_provider import FakeTelegramProvider
from app.services.telegram.telethon_provider import TelethonTelegramProvider


def new_provider() -> TelegramProvider:
    """Always returns a fresh instance — one Telethon client per account/session,
    never shared/cached across requests.
    """
    settings = get_settings()
    if settings.use_fake_telegram_provider:
        return FakeTelegramProvider()
    return TelethonTelegramProvider()
