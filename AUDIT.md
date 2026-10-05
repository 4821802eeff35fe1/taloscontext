# Release audit — v0.2.0

Evidence is from this workspace on 2026-10-05. Fake providers were used throughout. Production-like containers are not a claim of live Telegram/Timeweb verification or high-availability certification.

## Implemented

- Existing FastAPI/SQLAlchemy/Alembic/ARQ backend retained; 33 mapped tables, 114 HTTP operations in development configuration.
- Encrypted Redis Telegram login state with TTL and renewed locks; revocable web sessions, login/registration/Telegram rate limits, CSRF header and RBAC.
- Persisted background jobs/attempts, recovery/retry/cancel and actual Jobs UI.
- Content Studio: rich editor, nine transforms, safe live desktop/mobile Telegram preview, media attachment, revisions/diff/restore, dirty-state navigation protection, approval, scheduling and delivery status/retry/uncertain-outcome resolution.
- Calendar month/week/day, actual optimistic drag/reschedule with rollback and keyboard-accessible Change time. Timezone-aware schedules, seeded random slots, DST, windows/intervals/exclusions/pause and default RESCHEDULE_NEXT_SLOT misfire handling.
- Knowledge bases/upload/manual entries/search/preview/validity, Telegram result.json metadata, current-fact priority; Tone profiles and assignments; Series parts/context; Sources and Ideas.
- Redis pub/sub SSE across processes, reconnect/cache invalidation, notifications, audit, settings, masked configuration, costs and useful dashboard; ⌘K / Ctrl+K actions/search.
- Static responsive dark frontend behind Nginx; two-process backend, distinct worker/scheduler, Redis AOF, persistent storage volumes, non-root backend and pinned Python verification dependencies.

## Verified

- Full backend suite passes on SQLite/fakeredis and on PostgreSQL 16/Redis 7, using disposable test databases. 117 tests passed against PostgreSQL/Redis.
- Frontend: 25 Vitest/RTL tests, strict TypeScript, ESLint and production build pass.
- 8 Chromium Playwright scenarios passed against the actual seven-service Docker stack and static Nginx frontend: auth/dashboard, account/import/set, AI transform/history/approve/five deliveries, partial failure/retry without touching successes, actual calendar drag, Knowledge/Tone/schedule forms, system screens/palette/mobile layout, budget rejection and foreign-workspace denial.
- Docker restart acceptance: phone → backend restart → code completed; a QUEUED AI job and SCHEDULED post survived backend/worker/scheduler restart; five publications succeeded; second restart preserved publication ids, message ids and attempts. Actual MinIO upload/read, AI costs and Overview were checked.
- PostgreSQL migration upgrade → downgrade to base → upgrade succeeded; `alembic check` reported no schema differences. Also checked against the Compose application database.
- Security regression checks include route enumeration for workspace isolation, role/session/rate-limit/CSRF coverage, XSS/HTML conversion, private/CGNAT/mapped/multicast addresses, DNS-pinned HTTP Host/TLS SNI and redirect revalidation, owned renewable Redis leases, approval invalidation and billed malformed AI attempts.
- `npm audit --omit=dev`: zero reported vulnerabilities. Development audit retains the unpatched Tailwind 3 / braces advisory described below.

## Not verified live

- No real Telegram login, 2FA, publishing, FloodWait or metrics traffic.
- Timeweb pricing invoice reconciliation and real image traffic remain unverified. One successful live text generation is recorded below.
- No public HTTPS deployment, email/Telegram notification transport, backup restore drill, penetration test or large-scale load/soak test.
- Browser acceptance uses Chromium; other browsers and comprehensive assistive-technology testing remain unverified.

## Known limitations

- Telegram external sends and database commits cannot be atomic. A worker interrupted during send leaves delivery unknown; automatic retry is blocked until a person checks the actual channel.
- SSE uses transient Redis pub/sub, not an event replay log. Reconnect refetches affected workspace state. Some job types expose start/end progress rather than granular percentages.
- Knowledge retrieval and duplicate detection are local lexical heuristics, not guaranteed semantic understanding. Historical content is labeled and facts are prioritized; model correctness still needs review.
- Calendar week/day currently use date cards, not a fully timed hour-grid planner. UI filters generally use local page state. Workspace roles remain enforced by API; some forbidden UI actions produce a permission error instead of being hidden.
- Provider/storage keys, absolute session lifetime and infrastructure options are environment configuration shown read-only/masked in Settings. Settings edits general/CTA/budget/notification preferences; active-session revocation and member roles are interactive. Idle timeout is three days.
- Character-based token estimates can differ from provider billing. Concurrent workspace AI checks serialize through cost commit, but a provider timeout without usage cannot reveal the provider's actual charge. Daily/monthly billing boundaries use UTC.
- A process killed during Telegram AUTHORIZING can require starting a new flow. No browser cross-tab/reload auth-flow recovery list exists. Backend restart between phone and code is verified.
- The community MinIO reference image is built from pinned upstream source. Use supported storage/distribution for public production and keep infrastructure images patched.
- Tailwind 3's transitive `braces` has an [unpatched build-time recursion DoS advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm). Only trusted repository patterns/content enter builds. Nginx serves static output and does not run this dependency. Tailwind 4 migration remains planned.
- Registration remains public unless restricted by your deployment. TLS, secrets, registration policy, monitoring, backup/restore and scale limits must be configured for your environment.

## External API limitations

Timeweb's [Agent image-generation docs](https://timeweb.cloud/docs/ai-agents/manage-agents/image-generation) describe the external chat/widget path. The [API usage](https://timeweb.cloud/docs/ai-agents/api-usage) and [AI Gateway](https://timeweb.cloud/docs/ai-agents/api-usage/ai-gateway) documentation reviewed here did not establish a supported image endpoint for this adapter. The real image provider remains UNAVAILABLE even when credentials are set; generation controls are disabled with the requested explanatory tooltip. Upload and gallery remain usable.

Telethon access depends on account permissions, visibility and Telegram limits. Timeweb model selection belongs to the configured agent; client labels are not proof of the server's selected model.

## Final execution record

Release checks on 2026-10-05 (Europe/Moscow):

- Backend: 117/117 on SQLite/fakeredis and 117/117 on PostgreSQL/Redis; Ruff passed.
- Frontend: 25/25 Vitest/RTL; TypeScript, ESLint and production build passed.
- Actual Compose Chromium acceptance: 8/8, final run 41.0 seconds.
- Final restart acceptance passed for workspace `3180b408-3cb9-4a48-8467-1bc7c14ca897`, including Nginx API availability after backend replacement.
- Compose configuration validation and application-database Alembic check passed; dedicated migration database upgrade/downgrade/upgrade also passed.
- Loaded calendar desktop and 390 px mobile screenshots were inspected; mobile has no horizontal page overflow. This is a focused visual review, not a claim of exhaustive accessibility testing.

See TESTING.md and scripts/verify_compose.py for repeatable commands. All external providers were fake; MinIO, PostgreSQL, Redis, Nginx, backend processes, worker and scheduler were real containers.


## Re-verification of the documented quick start (2026-10-05)

The stack was rebuilt from the release commit and started with an env file copied verbatim from `.env.example`, as README instructs. This exposed two first-run defects, both fixed with regression tests:

- A blank numeric variable (`TELEGRAM_API_ID=`, as in the v0.1 template) made settings validation fail, so an upgraded `.env` crash-looped the backend container. Blank values now mean "unset".
- `.env.example` left `TELETHON_SESSION_ENCRYPTION_KEY` empty, so the first "Add Telegram account" (even with the fake provider) returned HTTP 500. The template now has `dev-only-` placeholders, production startup rejects them, and a missing key yields a 503 that names the variable.

After the fixes, on the rebuilt seven-container stack: backend 120 tests (SQLite) and the same suite on PostgreSQL 16 + Redis 7, Alembic upgrade/downgrade/upgrade + `alembic check`, frontend typecheck, 25 Vitest tests, production build, `docker compose config`, Playwright 8/8 against Nginx + API + worker + scheduler, and `scripts/verify_compose.py` (restart acceptance) — all passed. External providers remained fake; nothing here is a live Telegram or Timeweb verification.


## Post-deployment text-generation repair

On 2026-10-05, the server environment still contained `УКАЖИ_ID_АГЕНТА` in
TIMEWEB_AGENT_BASE_URL despite a configured agent id. Corrected that URL from the
configured id. A live request then exposed the agent model's HTTP 400 rejection of
temperature. Added bounded unsupported-parameter adaptation and six mocked HTTP
regressions; the current SQLite/fakeredis suite passed 126 tests and Ruff passed.
Installed the adapter in the server source and Python package. The original failed
content job subsequently completed successfully: DRAFT, 644 plain-text characters,
17810 input tokens, 1211 output tokens, recorded estimated cost 6.4436 RUB.
No Telegram publication was issued. This is a live text integration check, not
invoice reconciliation or a real Telegram verification.


## v0.3.0 — localization release (2026-10-05)

### Audit of parallel changes before localization

`git log`/`git diff` since v0.2.0 showed two commits made in parallel by Codex: `94f50aa` (Timeweb agent: bounded retry without parameters the reasoning model rejects, with mocked HTTP regressions) and `5e00176` (AUDIT note on live text generation). Both were reviewed and kept. No critical regressions were found: backend tests, Ruff, frontend typecheck/lint/tests/build, Alembic and `docker compose config` were green before any localization change. A later commit `670134d "Initial commit"` on `origin/main` snapshotted work in progress from this release; history was not rewritten (no force push) and the release commit builds on it.

### What changed

- Backend contract only (no presentation logic): error `code`/`details` on every error response, `users.language` + `PATCH /auth/me`, Telegram login flow `error_code`/`wait_seconds`, notification parameters (also in real-time events), search result `status`, failed-publication `error_code`, no English placeholders in data. Enums, AI prompts and tone logic are unchanged.
- Frontend: i18next with 12 namespaces × 2 languages; all pages and shared components translated; centralized labels for enums/audit/notifications/errors; `Intl` formatting; language switcher in Settings → General, header menu and sign-in page.
- Stored English texts that predate the parameters (old notifications, knowledge import warnings, job summaries) are mapped by known patterns; anything unrecognized is shown as stored rather than hidden. Raw technical messages (Telegram/AI exception text) are shown as "technical details" next to a localized description.

### Checks (local, fake providers)

- Backend: 132 passed on SQLite/fakeredis and 132 passed on PostgreSQL 16 + Redis 7; Ruff passed.
- Alembic: `bee55cb8fd0b` upgrade → check → downgrade → upgrade verified with data on PostgreSQL; `alembic check` on the Compose database reports no drift.
- Frontend: TypeScript, ESLint (0 warnings), Vitest 42 passed (17 new language tests), production build passed.
- Playwright against the rebuilt Compose stack (Nginx + 2 API processes + worker + scheduler + PostgreSQL + Redis + MinIO): 12/12 — the 8 existing product scenarios plus localization scenarios A (EN→RU in Settings, reload, fresh browser follows the account), B (RU→EN, reload), C (Russian UI leaves English post title/body untouched, stored data unchanged) and D (Calendar, Channels, Jobs, Costs, Settings in Russian: no English UI words, no horizontal overflow at 1280 px and 390 px).
- An additional ad-hoc Russian sweep over a workspace with imported channels, a published post, jobs and notifications covered all 22 routes, every Settings tab and the command palette; the only English words found were fake channel titles (data). Screenshots were reviewed for clipping.
- Static checks: every literal translation key used in code exists in both languages; en/ru key sets match (ru adds gender-specific status overrides); every Russian plural has `one/few/many/other`.
- The local `.env` used for Compose had an empty `TELETHON_SESSION_ENCRYPTION_KEY`, which (correctly) blocks adding even a fake Telegram account; the e2e run used a scratch copy with the documented `.env.example` dev key. The repository `.env` was not modified.

### Security review

Workspace isolation and RBAC are unchanged (no new workspace-scoped routes). `PATCH /auth/me` changes only the caller's own language/name, validates the language literal and goes through the CSRF header guard. Error `details` contain only values the caller already had (status, counts, budget figures, retry seconds) — no SQL, stack traces or secrets. Translations are rendered as React text (no HTML injection); post previews keep the existing sanitizer. Notification metadata in real-time events contains only masked phones and ids already present in the message. No secrets were added to code, docs or logs.

### Known limitations

- Pydantic validation messages (`VALIDATION_ERROR`) are shown inside a localized sentence but the field-level text is English.
- Exceptions from external services (Telegram, Timeweb) are shown as technical details in their original language.
- AI operations' revision labels and job summaries created before this release are mapped by pattern; unusual historical rows may show the stored English text.
