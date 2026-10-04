# Testing — v0.2.0

## Backend

Python 3.12 environment pinned by `backend/requirements.lock`. Default pytest uses SQLite with foreign keys enabled and fakeredis with Lua. Fake providers are enforced; network address tests mock DNS and HTTP.

```bash
cd backend
.venv/bin/pytest -q
.venv/bin/ruff check app tests
```

Optional real PostgreSQL and Redis:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://channelos:channelos@127.0.0.1:5432/channelos_tests \
TEST_REDIS_URL=redis://127.0.0.1:6379/15 .venv/bin/pytest -q
```

**Use disposable databases only.** Fixtures recreate the schema and flush the selected Redis database. Do not point at the application's PostgreSQL database or queue's Redis database. Migration round trips use another disposable database.

Coverage includes auth restart, 2FA state/secrets, rate limits/sessions/CSRF, jobs/recovery/idempotency, delivery/FloodWait/retry, all workspace routes, transforms/revisions/approval conflicts, Knowledge/exports/Tone/Series/Sources, schedule/DST/misfire, costs, notifications and audit. Additional regressions cover Redis lease renewal and outbound DNS pinning/redirect rejection.

## Frontend

```bash
cd frontend
npm ci
npm run typecheck
npm run lint
npm test
npm run build
npx playwright install chromium
E2E_BASE_URL=http://localhost:3000 E2E_API_URL=http://localhost:8000 npm run test:e2e
```

Vitest + React Testing Library cover budget rendering, publication/Channel Set/jobs states, editor action keys, Telegram HTML safety/conversion, calendar/DST math, realtime invalidation and cookie/CSRF/429 client behavior.

Playwright runs serially against the full fake-provider stack: register/login, account/channel import, channel-set creation, generate/transform/history/approve/publish, partial failure/retry with unchanged successful message ids, actual calendar drag, Knowledge/Tone/schedule forms, system screens/command palette/mobile width and budget/isolation rejection.

## Compose and restart acceptance

```bash
docker compose up -d --build
backend/.venv/bin/python scripts/verify_compose.py
```

Run this separately from Playwright: it intentionally restarts backend, worker and scheduler. It creates a fresh workspace, continues Telegram auth after an actual backend restart, preserves a queued generation and scheduled post, verifies five successful publications and unchanged message ids/attempts after another restart, then checks actual MinIO upload/read, costs and Overview. It also waits for the Nginx proxy to reconnect to backend.

The script requires development fake mode. Tests create retained test workspaces. Repeated suites may hit real auth rate limits; use an isolated test stack or wait for the indicated window. Do not weaken production limits to accommodate repeated tests.
