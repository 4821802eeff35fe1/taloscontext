# ChannelOS v0.3.0

A daily workspace for running a network of Telegram channels: accounts and Channel Sets, AI drafts and editing, approval, calendars and schedules, Knowledge and Tone of Voice, media, delivery history, costs, jobs, notifications and audit.

The main flow stays **one AI post → one DistributionBatch → independent Publication rows**. Distribution reuses the generated text; retry sends only failed channels. Telegram delivery with an uncertain outcome requires a human decision.

## Run locally with Docker

```bash
cp .env.example .env
docker compose up -d --build
```

Open http://localhost:3000 and create a workspace. The example enables fake Telegram, text and image providers; it makes no paid AI calls or real Telegram sends. `.env.example` ships `dev-only-…` placeholders for `APP_SECRET_KEY` and `TELETHON_SESSION_ENCRYPTION_KEY` so this works immediately; the API refuses to start with them when `APP_ENV=production`. Replace both with persistent secrets before connecting real accounts (changing the encryption key later makes stored Telegram sessions unreadable). Generate them with:

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

## Localization

The interface is available in **English** and **Russian**. Switch it in Settings → General → Interface language (or the language menu in the header; the sign-in page has an EN/RU toggle). The choice applies instantly, is stored in `localStorage` and in the user's account (`users.language`), so it follows the user to other devices.

Language priority: saved account preference → explicit local choice → browser locale (`ru`, `ru-RU`, `ru-*` → Russian, anything else → English) → English. A browser-inferred language is never written to the account.

The UI language does not change content: post text, titles, channel names, usernames, phone numbers, IDs and AI prompts/tone are never translated. Generate Russian posts from an English UI and vice versa.

Structure (`frontend/src/i18n/`):

- `index.ts` — i18next setup and language resolution; `language.ts` — `applyLanguage`, `intlLocale`.
- `locales/<lang>/<namespace>.json` — one file per namespace: `common` (navigation, actions, states, statuses, plurals), `auth`, `dashboard`, `content`, `channels`, `media`, `ai`, `analytics`, `automation`, `settings`, `system` (audit, notifications), `errors` (API error codes).
- `labels.ts` — the only place where machine values become text: `statusLabel(status, domain)`, `jobTypeLabel`, `auditActionLabel`, `notificationText`, `errorLabel`, etc. Components never compare languages or map enums themselves.
- `lib/format.ts` — dates, numbers, money and relative time via `Intl` in the current language (`5 окт. 2026 г., 23:42` / `Oct 5, 2026, 11:42 PM`; `1 250 430` / `1,250,430`; `1 249,52 ₽` / `RUB 1,249.52`). Timestamps stay UTC in the API.

Adding a key: add it to the namespace file for **every** language, then use `t("key")` with `useTranslation("<namespace>")` (or `t("ns:key")`). `npm test` includes language tests; keep `en` and `ru` files in sync.

Pluralization uses i18next suffixes — English `_one`/`_other`, Russian `_one`/`_few`/`_many`/`_other` — with `{{count, number}}` for locale-aware numbers: `1 пост`, `2 поста`, `5 постов`.

Statuses: backend enums (`PENDING_APPROVAL`, `FLOOD_WAIT`…) are unchanged. Their labels live under `common:status.any.<ENUM>` with optional per-domain overrides `common:status.<domain>.<ENUM>` (e.g. a publication `SUCCESS` reads "Опубликовано", a job `SUCCESS` reads "Выполнено"). Unknown enums fall back to a humanized value instead of an empty string.

API errors: the backend returns `code` + `details`; add the code to `errors.json` in each language to localize it. Unknown codes show the server message.

Adding a language: create `locales/<lang>/*.json` with the same keys, register them in `i18n/index.ts` (`SUPPORTED_LANGUAGES`, `resources`), add `<lang>` to the backend `Language` literal in `app/api/v1/auth.py` and the `intlLocale` mapping, and add plural forms that language needs.

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

## User documentation

- [Быстрый старт](docs/QUICK_START_RU.md) — первый запуск и первый пост за 5–10 минут.
- [Руководство пользователя](docs/USER_MANUAL_RU.md) — полное русскоязычное руководство по Web-панели.
- [Шпаргалка](docs/CHEATSHEET_RU.md) — статусы, основные действия и troubleshooting на каждый день.
