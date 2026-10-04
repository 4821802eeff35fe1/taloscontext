# Roadmap after v0.2.0

The daily workflow is implemented: persistent auth/jobs, Content Studio transforms and history, approval/delivery, calendar and schedule rules, Knowledge/Tone/Series, Sources/Ideas, SSE, settings, audit, notifications, costs and command search.

Next work, ordered by operational value:

1. Live credentialed Telethon and Timeweb acceptance on controlled test accounts; no live calls are claimed in v0.2.0.
2. Load/soak testing with many concurrent editors, SSE connections and workers; backup/restore drills and deployment monitoring.
3. Move reference MinIO to supported production storage; migrate Tailwind 3 to remove its unpatched build-only dependency advisory.
4. Add auth-flow recovery UI, stronger reservation/accounting of unknown provider spend, and richer notification progress.
5. Extend calendar week/day into hour grids and add editorial bulk actions, conflict guidance and deeper mobile accessibility checks.
6. Durable event replay/outbox where delivery of each notification is required; current SSE refetch-on-reconnect reconciles UI state.
7. More relevant Knowledge retrieval and semantic duplicate detection, with evaluations before introducing paid embeddings.
8. Email/Telegram notification channels and documented image API integration only if Timeweb publishes a supported programmatic endpoint.

Per-channel paid AI adaptation, billing/subscriptions and high-availability infrastructure are outside this release.
