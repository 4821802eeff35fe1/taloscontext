from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    audit,
    auth,
    autopilot,
    channels,
    content,
    distributions,
    jobs,
    knowledge,
    media,
    notifications,
    realtime,
    schedules,
    search,
    series,
    settings,
    sources,
    telegram_accounts,
    tone,
    workspaces,
)
from app.core.config import get_settings

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(telegram_accounts.router)
api_router.include_router(channels.router)
api_router.include_router(content.router)
api_router.include_router(distributions.router)
api_router.include_router(media.router)
api_router.include_router(settings.router)
api_router.include_router(analytics.router)
api_router.include_router(jobs.router)
api_router.include_router(autopilot.router)
api_router.include_router(sources.router)
api_router.include_router(realtime.router)
api_router.include_router(schedules.router)
api_router.include_router(knowledge.router)
api_router.include_router(tone.router)
api_router.include_router(series.router)
api_router.include_router(audit.router)
api_router.include_router(notifications.router)
api_router.include_router(search.router)

_settings = get_settings()
if _settings.use_fake_telegram_provider and not _settings.is_production:
    from app.api.v1 import dev

    api_router.include_router(dev.router)
