# Changelog

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
