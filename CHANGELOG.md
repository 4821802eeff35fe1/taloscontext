# Changelog

## v0.3.0

### Added

- Full Russian localization of the interface: every page, dialog, menu, form, table, empty/loading/error state, toast, confirmation, command palette and mobile navigation (i18next, namespaced JSON resources, English fallback).
- English/Russian switching in Settings → General, the header language menu and on the sign-in page; applies instantly without reload.
- Persistent user language preference: `users.language` (Alembic `bee55cb8fd0b`), `PATCH /auth/me`, optional `language` on registration; priority account → local choice → browser locale → English.
- Locale-aware dates, numbers, money, relative times and plural forms; centralized labels for content/publication/job/account/channel/series/idea/source statuses, job types, AI operations, audit actions and notification kinds.
- Machine-readable API errors: `{code, detail, details}` on every error (60+ codes, e.g. `AUTH_INVALID_CREDENTIALS`, `AUTH_RATE_LIMITED`, `BUDGET_EXCEEDED`, `TELEGRAM_FLOOD_WAIT`, `NO_POST_PERMISSION`, `WORKSPACE_ACCESS_DENIED`); Telegram login flows expose `error_code`/`wait_seconds`; notifications carry rendering parameters and real-time events include them.
- Performance page (per-channel views/forwards/reactions) wired into navigation; muted notification types are chosen from a list instead of free text.
- Vitest language suite (rendering, switching, persistence, browser fallback, account precedence, statuses, errors, formatting, pluralization) and Playwright localization scenarios.

### Fixed

- Russian times use a leading zero (`02:42`).
- API responses no longer embed English placeholders (`"Untitled"`, `"Post"`) in data; the client shows a localized fallback.
- Errors without a JSON body (proxy 502/504) produce a readable localized message instead of a raw status text.
- Settings → AI no longer appends English text to the model name.

No critical regressions were found in the parallel Codex changes (Timeweb unsupported-parameter adaptation, deployment notes); they were kept as-is. See AUDIT.md.

## v0.2.0

- Redis-persisted encrypted Telegram auth flows, renewed cross-process leases, rate limiting and revocable server-side web sessions.
- Persistent jobs, attempts, retries, cancellation, recovery and actual Jobs UI.
- Rich Content Studio with nine AI transforms, costs, revision diff/restore, dirty-state protection and safe Telegram previews.
- Month/week/day calendar, optimistic drag/reschedule, timezone-aware schedule rules, deterministic random slots, DST, exclusions, pause and misfire policy.
- Knowledge bases/import/search/validity, Telegram result.json metadata, Tone profiles/assignments, Series, Sources and Ideas.
- Redis pub/sub SSE with cache updates/reconnect, notifications, audit, settings, command palette, useful Overview and cost breakdown.
- Concurrency fixes for approvals, budgets, series and batch outcomes; DNS-pinned source requests; workspace-scoped fake failure controls; uncertain-delivery resolution.
- Responsive UI primitives, Vitest/RTL and Playwright acceptance scenarios.
- Static Nginx frontend, two-process API, persisted Redis AOF, pinned Python dependencies, non-root backend and source-built reference MinIO. Proxy re-resolves backend DNS after container restarts.

- First-run fixes found by re-running the documented quick start: blank numeric variables (e.g. `TELEGRAM_API_ID=` from a v0.1 `.env`) no longer crash-loop the API; `.env.example` ships `dev-only-` key placeholders (refused when `APP_ENV=production`), so adding a fake Telegram account works right after `cp .env.example .env`; a missing session-encryption key returns a clear 503 instead of an opaque 500.

See AUDIT.md for verification evidence, live verification gaps and known limits. Existing backend architecture and one-generation fan-out were retained.
