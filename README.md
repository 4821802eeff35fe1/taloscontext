# ChannelOS v0.2.0

A daily workspace for running a network of Telegram channels: accounts and Channel Sets, AI drafts and editing, approval, calendars and schedules, Knowledge and Tone of Voice, media, delivery history, costs, jobs, notifications and audit.

The main flow stays **one AI post → one DistributionBatch → independent Publication rows**. Distribution reuses the generated text; retry sends only failed channels. Telegram delivery with an uncertain outcome requires a human decision.

## Run locally with Docker

```bash
cp .env.example .env
docker compose up -d --build
```

Open http://localhost:3000 and create a workspace. The example enables fake Telegram, text and image providers; it makes no paid AI calls or real Telegram sends. Set persistent `APP_SECRET_KEY` and `TELETHON_SESSION_ENCRYPTION_KEY` before using real accounts. Generate them with:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Frontend is a static production build behind Nginx. API runs two Uvicorn processes; worker and scheduler run separately. PostgreSQL, Redis AOF and MinIO use persistent volumes. First build can take several minutes, including the pinned MinIO source build.

## Daily workflow

1. Accounts → add a Telegram account → phone, code, optional 2FA → imported channels.
2. Channel Sets → select channels and distribution mode.
3. Knowledge / Tone of Voice → add current facts, examples and an editorial profile.
4. Posts → generate or create a draft → edit in Content Studio → compare versions.
5. Submit → approve → publish now or choose an exact time / next schedule slot.
6. Calendar → drag a scheduled post or use Change time. Jobs and delivery details show actual execution and errors.
7. Costs, notifications and audit show spend, outcomes and changes. ⌘K / Ctrl+K opens actions and search.

`ADAPTED` per-channel paid regeneration is not exposed in this release. Image generation through the real Timeweb Agent is unavailable; upload/gallery remain usable. Fake image generation exists for testing.

## Development and checks

Python 3.12+, Node 22.12+ and Docker Compose are used for verification.

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/pip install --no-deps -e .
.venv/bin/pytest -q
.venv/bin/ruff check app tests
```

```bash
cd frontend
npm ci
npm run typecheck
npm test
npm run lint
npm run build
E2E_BASE_URL=http://localhost:3000 E2E_API_URL=http://localhost:8000 npm run test:e2e
```

Run browser tests against fake providers only. Run restart acceptance **separately** from browser tests:

```bash
backend/.venv/bin/python scripts/verify_compose.py
```

This script creates its own test workspace and restarts backend/worker/scheduler. Test databases must be disposable: the backend suite recreates its test schema. See [TESTING.md](TESTING.md).

See [AUDIT.md](AUDIT.md) for evidence and remaining limits, [DEPLOYMENT.md](DEPLOYMENT.md) for production setup, and [ARCHITECTURE.md](ARCHITECTURE.md), [TELEGRAM.md](TELEGRAM.md), [AI.md](AI.md), [SECURITY.md](SECURITY.md), [API.md](API.md), [DATABASE.md](DATABASE.md).
