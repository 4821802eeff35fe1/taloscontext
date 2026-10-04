# ChannelOS

A Telegram Content Operating System: connect Telegram accounts, organize their
channels into Channel Sets, generate one piece of AI content and fan it out to
every channel in a set without paying for regeneration, schedule and automate
publishing, and track AI spend against a budget.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the system design, and
[`AUDIT.md`](AUDIT.md) for what's implemented/tested vs. known limitations.

## Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2 (async), PostgreSQL, Alembic, Redis, ARQ, Telethon
- **Frontend**: React 19, TypeScript, Vite, TanStack Router/Query, Tailwind CSS, Radix UI
- **Media**: S3-compatible storage (MinIO in dev)

## Quick start (Docker)

```bash
cp .env.example .env
# fill in TELEGRAM_API_ID / TELEGRAM_API_HASH / TELETHON_SESSION_ENCRYPTION_KEY / APP_SECRET_KEY
# for a first run you can leave USE_FAKE_* flags at "true" and skip Timeweb/Telegram credentials entirely

docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs
- MinIO console: http://localhost:9001 (channelos / channelos-secret)

The `backend` service runs `alembic upgrade head` automatically on start.

## Running without Docker (what this session verified)

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

export APP_SECRET_KEY=dev-secret
export TELETHON_SESSION_ENCRYPTION_KEY=dev-encryption-key
export DATABASE_URL=sqlite+aiosqlite:///./dev.db   # Postgres in real deployments
alembic upgrade head
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

With `USE_FAKE_AI_PROVIDER=true`, `USE_FAKE_IMAGE_PROVIDER=true`,
`USE_FAKE_TELEGRAM_PROVIDER=true` (the defaults), the entire product flow —
add account, import channels, create a channel set, generate a post, approve,
schedule — works with zero real cost and zero real Telegram traffic. This
exact flow was run against a live `uvicorn` instance during development; see
AUDIT.md for details.

The background worker (`arq app.jobs.worker.WorkerSettings`) and scheduler
(`python -m app.jobs.scheduler`) require Redis — run them via
`docker compose up worker scheduler redis` or point `REDIS_URL` at a local
Redis instance.

## Tests

```bash
cd backend && source .venv/bin/activate
pytest -q          # 45 tests, no network/DB server required (SQLite in-memory)
ruff check app tests

cd frontend
npm run build       # tsc -b && vite build — exercises the full typecheck + bundle
```

## Repository layout

```
backend/app/
  api/v1/        REST endpoints
  core/          config, security, logging, RBAC, auth
  models/        SQLAlchemy models (one file per domain group)
  services/      business logic — ai/, telegram/, publishing/, scheduling/,
                 content/, costs/, analytics/, media/, security/, knowledge/
  jobs/          ARQ worker tasks + standalone scheduler process
  alembic/       migrations
frontend/src/
  features/      one folder per product area (auth, dashboard, telegram, ...)
  components/ui/ shared design-system primitives (Radix-based)
  lib/api.ts     typed API client
```
