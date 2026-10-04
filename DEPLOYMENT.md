# Deployment

## Docker Compose (reference deployment)

`docker-compose.yml` defines seven services: `postgres`, `redis`, `minio`,
`backend`, `worker`, `scheduler`, `frontend`. `backend` runs
`alembic upgrade head` before starting `uvicorn`; `worker` runs
`arq app.jobs.worker.WorkerSettings`; `scheduler` runs
`python -m app.jobs.scheduler` as its own long-lived process, per
ARCHITECTURE.md §4 (API / worker / scheduler are three separate processes,
never one).

```bash
cp .env.example .env   # fill in real secrets for anything beyond local dev
docker compose up --build
```

## Required environment for a real (non-fake) deployment

| Variable | Needed for |
|---|---|
| `APP_SECRET_KEY` | session cookie signing — **required** in production, startup fails without it |
| `TELETHON_SESSION_ENCRYPTION_KEY` | encrypting stored Telegram sessions — **required** in production |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | real Telethon client (from my.telegram.org) |
| `TIMEWEB_AGENT_API_KEY` | real text generation |
| `S3_*` | real media storage (any S3-compatible endpoint) |
| `USE_FAKE_*=false` | flips each provider from its fake implementation to the real one — flip them independently, not all at once, when validating a new environment |

## Database

- Run `alembic upgrade head` once per environment before starting the API.
- No `Base.metadata.create_all()` anywhere in application code — migrations
  are the only schema source of truth outside tests (which use an in-memory
  SQLite `create_all` specifically to stay hermetic).

## Backups

- **Postgres**: standard `pg_dump`/`pg_basebackup` (or your managed
  Postgres's snapshot feature) on a schedule; this project does not
  reimplement backup tooling. Nothing in the schema requires anything beyond
  that — all state is relational.
- **Media**: lives in S3-compatible storage (`media_assets.bucket` /
  `object_key`), not inside any container — back it up at the bucket level
  (versioning/replication on the S3 provider side), not by backing up a
  container volume.

## Health checks

- `GET /health` — liveness, no dependencies checked.
- `GET /health/ready` — checks Postgres (`SELECT 1`) and Redis (`PING`);
  returns `503` with a per-dependency breakdown if either is down. Point your
  orchestrator's readiness probe here, not at `/health`.

## Scaling notes

- `backend` is stateless beyond the DB/Redis — horizontally scalable.
- `worker` can run multiple replicas; ARQ's Redis-backed queue handles
  concurrent consumers, and `Publication` claiming is atomic at the DB level
  regardless of how many workers are running.
- `scheduler` must run as a **single** instance — it is a polling loop with
  in-memory de-duplication for the daily autopilot trigger
  (`_last_autopilot_run` in `app/jobs/scheduler.py`); running two instances
  would double-enqueue `autopilot_plan`. If this becomes a real constraint,
  move that de-dup key into Redis before scaling the scheduler out.
