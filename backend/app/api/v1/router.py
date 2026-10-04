from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    auth,
    autopilot,
    channels,
    content,
    distributions,
    jobs,
    media,
    settings,
    sources,
    telegram_accounts,
    workspaces,
)

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
