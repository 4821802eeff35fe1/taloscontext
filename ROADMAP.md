# Roadmap

Ordered by value to the core use case ("one post → many channels, under budget").

## Next (closes gaps against the original brief)

1. **Realtime push** — `main.py::ConnectionManager` exists; have `PublishingService`,
   `AIService` and job tasks broadcast status events (via Redis pub/sub so the
   worker process can reach API-held sockets). Replace Jobs-page polling.
2. **Job bookkeeping in the worker** — `jobs/tasks.py` has `_record_job` /
   `_mark_running` / `_mark_result` helpers; wire them around every task so the
   Jobs UI reflects real ARQ executions, and add exponential backoff via ARQ `Retry`.
3. **Image generation endpoint + UI action** — `AIService.generate_image` and
   `MediaService.store_generated` exist; add `POST /content/{id}/image` and the
   "Regenerate image" button. Activate a real provider once Timeweb documents one (AI.md).
4. **Rewrite / Shorten / Expand / Change tone** endpoints — `AIOperation` values
   and the `AIService` path exist; add thin endpoints + editor buttons.
5. **Workspace CTA defaults** — currently passed as `{}` from the schedule endpoint;
   add a `workspace_settings` table and Settings UI.
6. **Calendar (month/week/day) with dnd-kit drag-to-reschedule.**
7. **Schedules CRUD API + UI** — `ScheduleService` is implemented and tested;
   only the REST surface and UI are missing.
8. **Cross-channel analytics UI** — `AnalyticsService.content_item_totals` exists;
   add metrics refresh scheduling and the per-content table/chart.
9. **Notifications + Audit log writes** — models exist; emit rows from services.
10. **Tone of Voice / Knowledge / Series / Ideas UIs** — models and services exist.
11. **⌘K command palette, cursor pagination, Vitest + Playwright suites.**

## Later

- Move duplicate scoring onto a `pg_trgm` GIN index for large histories.
- Redis-backed de-dup for the scheduler's daily autopilot trigger (allows >1 replica).
- Telegram/email notification providers behind the existing notification abstraction.
- ADAPTED channel-set mode (per-channel AI adaptation, opt-in, billed per channel).
