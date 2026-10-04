"""ARQ worker process entrypoint: `arq app.jobs.worker.WorkerSettings`."""
from typing import ClassVar

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.jobs.tasks import autopilot_plan, source_fetch, telegram_publish, telegram_refresh_metrics

configure_logging()
settings = get_settings()


class WorkerSettings:
    functions: ClassVar[list] = [telegram_publish, telegram_refresh_metrics, source_fetch, autopilot_plan]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10
    job_timeout = 120
