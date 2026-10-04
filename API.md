# API — v0.2.0

REST prefix `/api/v1`. Swagger at `/docs` and OpenAPI at `/openapi.json` are the exact contract: **114 HTTP operations** in the verified development configuration (including two health routes and the fake-only control). Production omits the development control.

Cookie auth is `channelos_session`, a signed server-side session id. Mutations require `X-ChannelOS-Client`; browser client always sends it. Workspace routes check membership/role and foreign references. 429 responses expose Retry-After; 402 identifies budget rejection; 409 identifies invalid transitions/conflicts.

Main route families:

| Family | Operations |
|---|---|
| `/auth` | register, login, logout, me, sessions, revoke-others |
| `/workspaces` | list; workspace members and role changes |
| `/workspaces/{ws}/telegram` | accounts, auth/start, auth/{flow}, code, password, refresh-channels, disconnect, delete |
| `/workspaces/{ws}/channels` | list and settings |
| `/workspaces/{ws}/channel-sets` | create/list/details/update/delete |
| `/workspaces/{ws}/content` | manual create, background generate, list/details/edit, transform, revisions/restore, costs/context, approval/rejection, schedule/reschedule/unschedule, publish-now, archive/delete, calendar |
| `/workspaces/{ws}/distributions` | delivery batches, retry-failed, resolve uncertain publication |
| `/workspaces/{ws}/jobs` | filtered cursor pages, details/attempts, retry/cancel |
| `/workspaces/{ws}/schedules` | CRUD, pause, preview |
| `/workspaces/{ws}/knowledge` | bases, documents, uploads, parsed preview, search |
| `/workspaces/{ws}/tone-profiles` | CRUD/default |
| `/workspaces/{ws}/series` | CRUD, part/progress details |
| `/workspaces/{ws}/sources` and `/ideas` | source CRUD/fetch; inbox/filter/status |
| `/workspaces/{ws}/media` | paged gallery, upload, generate/status, details/archive, authenticated bytes |
| `/workspaces/{ws}/analytics` | costs, dashboard, content, channel performance |
| `/workspaces/{ws}/settings` | general, budget, notifications, masked provider/storage/security status |
| `/workspaces/{ws}/audit`, `/notifications`, `/search` | filters, read actions, global search |
| `/workspaces/{ws}/events` | SSE, cookies required, Redis pub/sub |
| `/health`, `/health/ready` | API liveness and dependency/process status |

Generate returns `{content, job}` with 202. Transforms/imports/fetches return persisted jobs. Job records are committed before dispatch. List response shapes are explicitly typed in `frontend/src/lib/api.ts`; several lists use `{items,next_cursor}`, and jobs additionally return status counts.

Telegram login routes changed from v0.1 account-id/in-memory login to flow-id/Redis login. Frontend and backend must be deployed together. The browser client and OpenAPI are authoritative over historical snippets.
