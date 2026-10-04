# Audit

Final state of this build, written to be read by someone deciding whether to
deploy it. "Tested" below always says *how* — fake providers and unit tests
are not live Telegram/Timeweb traffic.

## Implemented

**Backend (FastAPI, SQLAlchemy 2 async, Alembic, ARQ)**
- 30-table domain model covering every entity in the brief; UUID keys,
  `TIMESTAMPTZ` everywhere, money as `NUMERIC(12,4)`.
- Auth: email/password (Argon2), signed HttpOnly session cookie, 5-role RBAC
  enforced server-side on every mutating endpoint.
- Telegram: full Telethon login flow (phone → code → 2FA), Fernet-encrypted
  `StringSession`, encrypted + masked phone, channel import with real
  post-permission detection, connect/disconnect/delete/refresh.
- Channel Sets with EXACT / CTA_PER_CHANNEL / CONTACT_PER_CHANNEL modes; CTA
  resolver with channel → workspace → none precedence.
- Content: controlled state machine (12 statuses, single transition table),
  revisions, Telegram-HTML sanitizer applied before persistence.
- AI: provider abstraction (`TextAIProvider` / `ImageAIProvider` /
  `SearchProvider`), Timeweb Agent text client (`/chat/completions`), one call
  per post with structured JSON + Pydantic validation + max one retry.
- Cost engine: per-request `AIRequest` (raw usage, rate snapshot, Decimal
  costs), `CostEvent` ledger, today/month/forecast, budget guard
  (daily/monthly/per-post) used by Autopilot.
- Distribution: one `ContentItem` → one `DistributionBatch` → N independent
  `Publication`s with unique idempotency keys; atomic claim; batch outcome
  (SUCCESS / PARTIAL_FAILURE / FAILED) mirrored onto the content status;
  retry re-queues only failed publications.
- FloodWait: account-level wait window, publication stays `PENDING`, scheduler
  skips the account until the window passes, account returns to `CONNECTED`
  after the next successful send. RPC errors classified (permission / entity /
  auth / network).
- Scheduler process: promotes due content, drives every pending publication
  (first send, FloodWait, network retry, manual retry) with ARQ job-id dedup;
  daily Autopilot trigger. `ScheduleService` expands windows/days/exclusions/
  min-interval in the schedule's timezone.
- Autopilot: MANUAL / APPROVAL / AUTOPILOT, weighted category mix, budget
  guard before generation, routes risky / duplicate / source-less news posts
  to approval instead of auto-publishing.
- Duplicate detection without AI calls (shingle Jaccard + SimHash + tags/category).
- Knowledge base ingestion incl. Telegram Desktop JSON export importer.
- Sources: RSS fetch with SSRF guard and URL liveness check → Ideas inbox.
- Media: S3/MinIO storage (never base64 in DB), magic-byte MIME sniffing,
  15 MB bounded read, filename sanitization, membership-checked content endpoint.
- Analytics: Telethon metric snapshots (read-only counters), per-content
  cross-channel totals.
- Health: `/health`, `/health/ready` (Postgres + Redis). Structured JSON logs
  with request id and secret-field redaction.
- Docker Compose with all 7 services; backend runs `alembic upgrade head` on start.

**Frontend (React 19, TS strict, Vite, TanStack Router/Query, Tailwind, Radix)**
- Dark SaaS design system; Radix Dialog/Select/Switch (no native select/dialog).
- Pages: Login/Register, Overview dashboard, Telegram Accounts (3-step login
  dialog), Channels (grid, autopilot toggle), Channel Sets (create with
  channel picker), Posts (master–detail Content Studio with Telegram preview,
  edit, submit/approve/reject/schedule), **per-channel distribution panel
  with "N / M published" and "Retry K failed"**, Approval Queue, Media
  Gallery (upload + grid), AI Cost Dashboard (budget bar, forecast, provider
  status incl. honest image-provider-unavailable state), Jobs, Autopilot settings.
- Visible dev-mode banner whenever any fake provider is active.

## Tested

| What | How | Result |
|---|---|---|
| Backend unit/integration suite | `pytest` on in-memory SQLite, fake providers | **45 passed** |
| Full publish path | `PublishingService` × 3 publications via `FakeTelegramProvider` | all SUCCESS, batch SUCCESS, content PUBLISHED, re-run sends nothing |
| Lint | `ruff check app` | 1 style notice left (nested `if` in fake provider) |
| Frontend typecheck + production build | `tsc -b && vite build` | clean |
| Migrations | `alembic revision --autogenerate` → `upgrade head` → `alembic check` | 30 tables, no drift |
| API surface | `app.openapi()` | 37 paths |
| Compose file | parsed; 7 services present | ok |
| Live vertical slice | running `uvicorn` + curl: register → Telegram login (fake) → import 5 channels → Channel Set → generate (fake AI) → cost ledger +1 call → submit → approve → schedule | 1 ContentItem, 1 DistributionBatch, 5 Publications with distinct idempotency keys (checked in the DB) |
| Frontend dev server | `npm run dev` | serves 200 |

## Not tested (and why)

- **Real Telegram** — no `TELEGRAM_API_ID/HASH` or test account in this
  environment. The Telethon provider is written against Telethon's public API
  but has never sent a real message.
- **Real Timeweb Agent** — no `TIMEWEB_AGENT_API_KEY`. The client follows the
  documented OpenAI-compatible shape; response parsing and retry are covered
  only via the fake provider.
- **Worker + scheduler against real Redis, Postgres, MinIO** — Docker was not
  available and installing Redis needed elevated permissions this session did
  not take unilaterally. The service code those processes call is covered by
  the tests above; the processes themselves have not been run.
- **Frontend automated tests** — no Vitest/RTL or Playwright suites were
  written. The UI was verified by typecheck, production build and the API
  calls it makes being exercised live, not by clicking through every page.

## Known limitations

- **Telegram login state is in-process** (`_PENDING_LOGINS`): run the API with a
  single worker process, or a login started on one process can't be finished
  on another. Fix: keep the pending Telethon session in Redis (encrypted).
- **Stale CLAIMED/SENDING publications** after a worker crash are deliberately
  not re-sent automatically (we can't know whether Telegram received them).
  They need a manual decision; there is no UI for it yet.
- **Network-error retries** are driven by the 15 s scheduler tick with an
  attempt cap of 5 — no exponential backoff yet.
- **Job rows**: `Job`/`JobAttempt` helpers exist but ARQ tasks don't write them
  yet, so the Jobs page stays empty in a real deployment.
- **Realtime**: the WebSocket endpoint exists but nothing publishes to it;
  the UI uses targeted polling (distribution panel only while in flight, Jobs page).
- **Not built yet** (models/services exist for most): image generation
  endpoint + UI, Rewrite/Shorten/Expand/Tone actions, workspace CTA defaults
  (currently `{}`), Schedules CRUD UI, Calendar + drag & drop, Tone of Voice /
  Knowledge / Series / Ideas / Notifications / Audit Log / Settings pages,
  ⌘K palette, cursor pagination, analytics charts, mobile layout polish.
  See ROADMAP.md for order.
- `boto3` calls are synchronous inside async handlers — fine at low volume,
  should move to a thread pool or `aioboto3` under load.
- Scheduler must run as a single replica (in-memory autopilot de-dup).

## External provider limitations

- **GPT Image 2.5 Sunburst**: the Timeweb docs reviewed describe agent image
  generation only via the hosted chat/widget, not a programmatic Images API.
  No endpoint was invented; `TimewebGatewayImageProvider` reports
  `UNAVAILABLE` until `TIMEWEB_AI_GATEWAY_*` and `TIMEWEB_IMAGE_MODEL` are set
  *and* `generate()` is implemented against a confirmed endpoint. Text
  generation and publishing are unaffected. See AI.md.
- The Timeweb agent's `model` field is not relied on to select GPT-6 Sol —
  the agent's console configuration decides.
- Docs pages were not fetched during this session; the integration follows
  the facts given in the brief (base URL, `/chat/completions`, Bearer auth,
  no Images API). Re-check against current Timeweb docs before go-live,
  especially token limits and supported request parameters for GPT-6 Sol.

## Security notes

Fixed during the final review:
- **IDOR**: Telegram account actions, Channel Set creation (foreign
  `channel_ids`) and content analytics did not verify workspace ownership.
  All now check it; covered by a regression test for the account service.
- **Media** was exposed via presigned URLs to an internal hostname; now served
  through a membership-checked endpoint. Upload reads are bounded.
- Naive `datetime.utcnow()` replaced with timezone-aware UTC.

Still open:
- No HTTP rate limiting / brute-force protection on `/auth/login` — put a
  reverse proxy limit in front, or add one before exposing publicly.
- No CSRF token; mitigated by `SameSite=Lax` cookies and JSON-only mutating
  endpoints, but worth adding before multi-tenant production use.
- Session cookies can't be revoked server-side before expiry (14 days); a
  session table would allow logout-everywhere.
- In development without `APP_SECRET_KEY`, cookies are signed with a fixed
  dev secret. Production refuses to start without one.
- `npm audit` reports advisories in dev dependencies; not triaged.

## Next steps

1. Run `docker compose up --build` on a machine with Docker; confirm worker +
   scheduler publish the scheduled batch end-to-end with fake providers.
2. Add real `TELEGRAM_API_ID/HASH` + a test account and a throwaway channel;
   flip only `USE_FAKE_TELEGRAM_PROVIDER=false` and publish one post.
3. Add the Timeweb key; flip `USE_FAKE_AI_PROVIDER=false`; compare
   `AIRequest` token counts and cost against the Timeweb billing console.
4. Move pending Telegram logins to Redis; write Job rows from ARQ tasks;
   push realtime events.
5. Work through ROADMAP.md "Next".
