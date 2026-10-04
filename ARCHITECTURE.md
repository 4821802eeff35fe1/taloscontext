# ChannelOS — Architecture

ChannelOS is a Telegram Content Operating System: one piece of AI-generated content
(`ContentItem`) is produced once and fanned out to many Telegram channels as independent
`Publication` records. This document is the contract the implementation follows.

## 1. Core principle: Content vs Distribution

```
ContentItem (1 AI call, 1 optional image)
    └── DistributionBatch (created on approve/schedule)
            ├── Publication -> @channel_1
            ├── Publication -> @channel_2
            └── Publication -> @channel_N
```

- AI is invoked **once** per ordinary post (see §5).
- Telegram delivery is **per channel**, **per publication**, each independently retryable.
- A failed publication never triggers regeneration of content or re-sending succeeded ones.

## 2. Services (backend/app/services)

| Service | Responsibility |
|---|---|
| `AIService` | Talks to `TextAIProvider`/`ImageAIProvider`, persists `AIRequest`/cost rows, enforces budget guard, retries once on malformed JSON |
| `TelegramAccountService` | Telethon login flow (phone → code → 2FA), encrypted `StringSession` storage, health/heartbeat |
| `TelegramChannelService` | Imports dialogs the account administers, permission checks, health |
| `ContentService` | CRUD + state machine for `ContentItem`/`ContentRevision`, calls `AIService`, calls `DuplicateDetectionService` |
| `DistributionService` | Resolves a `ChannelSet` + distribution mode (EXACT/CTA_PER_CHANNEL/CONTACT_PER_CHANNEL/ADAPTED) into a `DistributionBatch` + `Publication` rows |
| `PublishingService` | Claims a `Publication` atomically, calls `TelegramProvider.send`, records result, classifies Telegram RPC errors (FloodWait, permission, etc.) |
| `ScheduleService` | Expands `ScheduleRule` (windows, days, randomization, timezone) into concrete `scheduled_at` UTC timestamps |
| `AutopilotService` | Daily planner: content mix, budget guard, creates `ContentItem`s in MANUAL/APPROVAL/AUTOPILOT modes |
| `MediaService` | S3-backed asset storage, `MediaAsset`/`MediaGeneration` bookkeeping |
| `CostService` | Pricing snapshot, `CostEvent` ledger, budget checks, dashboard aggregation |
| `AnalyticsService` | Pulls view/forward/reaction snapshots via Telethon, aggregates per content/channel |
| `KnowledgeService` | Ingests knowledge documents (incl. Telegram JSON export importer), chunking for prompt context |
| `DuplicateDetectionService` | Cheap local duplicate scoring: trigram similarity + SimHash + tags/category, no extra AI call |
| `SourceService` | RSS/URL/web-search ingestion into Ideas Inbox, URL sanity checks |
| `CTAResolverService` | Resolves `cta_key` → contact string with channel → workspace → none precedence |

Call direction is strictly one-way: `AI → ContentItem → Approval/Scheduler → Distribution →
Publication Job → Telethon`. The AI layer never touches Telegram directly.

## 3. Database schema (SQLAlchemy 2 / Postgres)

Grouped by domain; see `backend/app/models/*.py` for the authoritative columns.

- **Identity**: `User`, `Workspace`, `WorkspaceMember` (role: OWNER/ADMIN/EDITOR/APPROVER/VIEWER)
- **Telegram**: `TelegramAccount` (encrypted session, status enum, flood_wait_until), `TelegramChannel` (health enum, permissions, tone/knowledge FK), `ChannelSet`, `ChannelSetMember`
- **Content**: `ContentItem` (status state machine), `ContentRevision`, `ContentSeries`, `SeriesItem`
- **Media**: `MediaAsset` (bucket/key/mime/dimensions/checksum — never base64 in DB), `MediaGeneration`
- **Distribution**: `DistributionBatch`, `Publication` (idempotency_key unique, telegram_message_id)
- **Scheduling**: `Schedule`, `ScheduleRule`, `AutopilotConfig`
- **Cost**: `AIRequest`, `AIUsage`, `CostEvent` (all money as `Numeric(12,4)`, never float)
- **Knowledge**: `KnowledgeDocument`, `KnowledgeChunk`, `ToneOfVoiceProfile`
- **Sources**: `Source`, `SourceItem`
- **Analytics**: `PostMetricSnapshot`
- **Ops**: `Job`, `JobAttempt`, `Notification`, `AuditLog`

All timestamps are `TIMESTAMPTZ`, stored UTC, converted to channel/user timezone only at the
presentation layer. All FKs cascade per workspace ownership; cross-workspace access is denied
at the repository layer, not just in the API.

## 4. Worker architecture

- **API process** (FastAPI/uvicorn): request/response, enqueues jobs, never blocks on Telegram/AI.
- **Worker process** (ARQ + Redis): executes `Job` rows — `AI_GENERATE_POST`, `AI_GENERATE_IMAGE`,
  `TELEGRAM_PUBLISH`, `TELEGRAM_REFRESH_CHANNELS`, `TELEGRAM_REFRESH_METRICS`, `SOURCE_FETCH`,
  `AUTOPILOT_PLAN`. Each job row tracks `attempt`/`max_attempts`/`error`/timestamps.
- **Scheduler process**: a lightweight loop (APScheduler-style cron tick backed by the same Redis)
  that expands `ScheduleRule`s into due `Publication`s and enqueues `TELEGRAM_PUBLISH` jobs, and
  runs `AUTOPILOT_PLAN` once per workspace per day.
- Idempotency: `Publication.idempotency_key` is unique; the worker claims a row with
  `UPDATE ... WHERE status = 'PENDING' RETURNING ...` (atomic claim), so a worker restart cannot
  double-send. FloodWait sets `flood_wait_until` on the account and reschedules the job rather
  than retrying immediately; network errors use exponential backoff; permission/entity errors
  fail the publication without retry.

## 5. AI flow

```
ContentService.generate()
  -> KnowledgeService.build_context(channel/series/tone)
  -> DuplicateDetectionService.recent_fingerprints(targets)
  -> AIService.complete(system_prompt, context)      # ONE call, JSON-only response
       -> TextAIProvider (Timeweb OpenAI-compatible /chat/completions)
       -> parse+validate against GenerationResult (Pydantic)
       -> on parse failure: ONE automatic retry, else raise
  -> CostService.record(AIRequest usage, pricing snapshot)
  -> DuplicateDetectionService.score(result.duplicate_fingerprint)
  -> persist ContentItem + ContentRevision
```

Regeneration (Rewrite/Shorten/Expand/Change Tone/Regenerate image) are explicit user-triggered
AI calls, billed and logged the same way, never implicit.

`TextAIProvider` targets Timeweb's OpenAI-compatible agent endpoint
(`TIMEWEB_AGENT_BASE_URL` + `/chat/completions`). `ImageAIProvider` is an interface with a
`FakeImageProvider` (dev) and a `status()` of `UNAVAILABLE` by default for any real backend,
because current Timeweb docs do not expose a programmatic Images API for the agent — see
`AI.md` for the exact decision and how to wire a real provider the moment one is confirmed.

## 6. Telegram flow

```
Add Account -> phone -> Telethon.send_code_request()
            -> code  -> Telethon.sign_in()  [may raise SessionPasswordNeededError]
            -> 2FA?  -> Telethon.sign_in(password=...)
            -> StringSession exported, encrypted (Fernet/AES via cryptography), stored
            -> profile + dialogs fetched -> TelegramChannel rows upserted, permission checked
```

No verification code, 2FA password, or plaintext session is ever persisted. Session strings are
encrypted with `TELETHON_SESSION_ENCRYPTION_KEY` before the row is written; the key is never
logged, and structlog processors redact any field named `session`, `password`, `code`, `token`.

## 7. Publishing state machine

`ContentItem`: `IDEA → DRAFT → GENERATING → PENDING_APPROVAL → APPROVED → SCHEDULED → PUBLISHING
→ PUBLISHED | PARTIALLY_PUBLISHED | FAILED`, with `REJECTED`/`ARCHIVED` reachable from the
pre-publish states. Transitions are enforced by `ContentService._assert_transition`, a single
source of truth for allowed transitions; orchestration also checks it before changing status.

`Publication`: `PENDING → CLAIMED → SENDING → SUCCESS | FAILED (→ retryable)`. A
`DistributionBatch` aggregates its publications' statuses into `SUCCESS` /
`PARTIAL_FAILURE` / `FAILED`; the UI replays only the `FAILED` publications, never the
succeeded ones.

## 8. Cost flow

Every provider call producing billable usage writes one `AIRequest` row with raw provider usage
plus the pricing snapshot in effect at call time (rates are DB-configurable, not hardcoded).
`CostEvent` is the denormalized ledger `CostService` reads for dashboards (today/week/month,
by channel, by channel set, by category, by provider). `BudgetGuard` checks workspace
daily/monthly/per-post caps **before** an AI call is issued; at 100% of a cap, Autopilot AI
generation pauses — publishing of already-approved content is never blocked by AI budget.

## 9. Security model

- Argon2 password hashing, secure HttpOnly session cookies, RBAC enforced server-side on every
  mutating endpoint (never trust frontend role gating).
- Telethon sessions encrypted at rest; phone numbers masked in API responses by default.
- Upload pipeline validates MIME by content sniffing (not extension), enforces size limits,
  sanitizes filenames.
- Outbound URL fetchers (`SourceService`, link preview) block private/link-local/metadata IP
  ranges (SSRF guard) before issuing a request.
- `structlog` processor redacts secret-shaped fields; no token/session/password ever logged.
- Missing `APP_SECRET_KEY` in a non-development `APP_ENV` fails application startup.

## 10. API shape

Versioned REST under `/api/v1`, resources per §45 of the product brief. Mutating endpoints are
transactional (single DB transaction per request handler); list endpoints use cursor pagination
(`posts`, `audit-log`, `jobs`, `media`). Realtime state (`job status`, `publishing progress`,
`floodwait`, `account disconnected`) is published through Redis pub/sub and delivered through
`/api/v1/workspaces/{workspace_id}/events` SSE. Reconnect refetches workspace queries;
there is no durable event replay log.


## 11. v0.2 operational architecture

Telegram auth flows persist encrypted temporary StringSession, phone and phone-code hash
in Redis with a ten-minute TTL. Verification codes and 2FA passwords are used only during
the request. Owned, renewing Redis leases serialize flow mutations and scheduler ticks.
Completed account state commits to PostgreSQL before the flow is marked completed.

Web cookies contain a signed session id referencing revocable `user_sessions` rows.
Jobs and attempts persist in PostgreSQL; ARQ messages carry job ids. The scheduler
recovers lost queued messages and stale work. Two API processes run in the verified
Compose deployment. SSE releases its request database connection and rechecks access.

Publication claims commit before external Telegram sends. Uncertain delivery blocks
automatic retry and requires manual reconciliation: Telegram sends and database commits
cannot be atomic. Content and batch locks serialize edits, approval and final aggregation.
AI budget checks lock the workspace through usage/cost commit; malformed billed outputs
remain in the ledger.

Nginx serves the production frontend and proxies API/SSE using Docker DNS resolution,
including after backend container replacement. Redis AOF and database/storage volumes
preserve state. External URL retrieval pins validated public addresses and revalidates
redirects while preserving Host and TLS SNI.
