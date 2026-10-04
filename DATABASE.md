# Database

PostgreSQL via SQLAlchemy 2 (async, `asyncpg`), migrated with Alembic. The
schema is defined once in `backend/app/models/*.py` and the initial migration
`backend/alembic/versions/*_init.py` was generated with
`alembic revision --autogenerate` and applied successfully against a real
database during development (see AUDIT.md for how it was verified without
Docker/Postgres available in this environment).

## Tables by domain

| Domain | Tables |
|---|---|
| Identity | `users`, `workspaces`, `workspace_members` |
| Telegram | `telegram_accounts`, `telegram_channels`, `channel_sets`, `channel_set_members` |
| Content | `content_items`, `content_revisions`, `content_series`, `series_items` |
| Media | `media_assets`, `media_generations` |
| Distribution | `distribution_batches`, `publications` |
| Scheduling | `schedules`, `schedule_rules`, `autopilot_configs` |
| Cost | `ai_requests`, `cost_events` |
| Knowledge | `knowledge_documents`, `knowledge_chunks`, `tone_of_voice_profiles` |
| Sources | `sources`, `source_items` |
| Analytics | `post_metric_snapshots` |
| Ops | `jobs`, `job_attempts`, `notifications`, `audit_logs` |

33 tables total. All primary keys are UUIDv4; all timestamps are
`TIMESTAMPTZ` stored in UTC; all money columns are `NUMERIC(12,4)` (never
`FLOAT`).

## Key constraints

- `publications.idempotency_key` is `UNIQUE` — this, combined with the
  atomic `UPDATE ... WHERE status='PENDING'` claim in `PublishingService`, is
  what makes a publish job safe to re-run after a worker crash.
- `workspace_members` is the only path from a `User` to a `Workspace`; every
  query that touches workspace-scoped data filters by `workspace_id` taken
  from the authenticated membership, never from a client-supplied value
  alone.
- `AutopilotConfig.workspace_id` is `UNIQUE` — one config per workspace,
  created lazily on first read (`autopilot.py::_get_or_create`).

## Why Postgres full-text/trigram features aren't in the schema yet

The product brief calls for `pg_trgm` similarity as part of duplicate
detection. The implemented `DuplicateDetectionService` computes trigram
(shingle) Jaccard similarity and SimHash **in Python** against recently
published `ContentItem`s loaded from Postgres, rather than pushing the
similarity computation into a `pg_trgm` index/operator. This was a
deliberate scope choice: it keeps duplicate detection fully testable without
a Postgres-specific extension and with zero additional AI cost (see AI.md
§"Duplicate detection"). Migrating the comparison to a `pg_trgm` GIN index
for performance at scale (thousands of historical posts) is a reasonable
follow-up — see ROADMAP.md — and would not change the service's public
interface.

## Migrations

```bash
# generate a new migration after changing models/*.py
alembic revision --autogenerate -m "describe the change"

# apply
alembic upgrade head
```

`app/db/base.py::Base` is the single `DeclarativeBase`; `alembic/env.py`
imports `app.models` (which re-exports every model) before computing
`target_metadata`, so no table is silently excluded from autogenerate.


## v0.2.0 schema

33 mapped tables. The second Alembic revision adds persistent user sessions, workspace settings and knowledge bases, expands job/attempt tracking, content revisions/context and schedule/series metadata. Upgrade, downgrade, repeated upgrade and `alembic check` were exercised on PostgreSQL 16. Do not run the destructive test fixture against an application database; use a separate disposable test database.
