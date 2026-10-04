"""ARQ worker process entrypoint: `arq app.jobs.worker.WorkerSettings`.

There is one ARQ function, `run_job`, which executes a persisted Job row by
id; the job's type picks the handler (app/jobs/handlers.py).
"""
import uuid
from typing import ClassVar

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.jobs.service import run_job as run_persisted_job
from app.services.system.health import WORKER_HEARTBEAT_KEY, beat

configure_logging()
settings = get_settings()


async def run_job(ctx, job_id: str) -> None:
    await run_persisted_job(uuid.UUID(job_id))


async def heartbeat(ctx) -> None:
    await beat(WORKER_HEARTBEAT_KEY)


async def startup(ctx) -> None:
    import app.jobs.handlers  # noqa: F401  (register handlers before the first job)

    await beat(WORKER_HEARTBEAT_KEY)


class WorkerSettings:
    functions: ClassVar[list] = [run_job]
    cron_jobs: ClassVar[list] = [cron(heartbeat, second={0, 30}, run_at_startup=True)]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10
    job_timeout = 600
    max_tries = 1  # retries are decided by the Job row, not by ARQ
