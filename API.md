# API

Versioned REST under `/api/v1`, served by FastAPI; full interactive reference
at `/docs` (Swagger UI) once the backend is running. 37 paths registered —
verified with `app.openapi()` during development (AUDIT.md).

Cookie-based session auth (`channelos_session`, HttpOnly). All
workspace-scoped endpoints take `workspace_id` in the path and re-check
membership + role server-side on every call (`core/rbac.py`).

## Auth

| Method | Path | Notes |
|---|---|---|
| POST | `/auth/register` | creates `User` + `Workspace` + `OWNER` membership |
| POST | `/auth/login` | sets session cookie |
| POST | `/auth/logout` | clears session cookie |
| GET | `/auth/me` | current user |

## Workspaces

| Method | Path |
|---|---|
| GET | `/workspaces` |

## Telegram accounts

| Method | Path | Notes |
|---|---|---|
| GET | `/workspaces/{ws}/telegram/accounts` | |
| POST | `/workspaces/{ws}/telegram/accounts/login` | `{phone}` → sends code |
| POST | `/workspaces/{ws}/telegram/accounts/{id}/verify` | `{code}` → may require 2FA |
| POST | `/workspaces/{ws}/telegram/accounts/{id}/2fa` | `{password}` |
| POST | `/workspaces/{ws}/telegram/accounts/{id}/channels` | imports administered channels |
| POST | `/workspaces/{ws}/telegram/accounts/{id}/disconnect` | |
| DELETE | `/workspaces/{ws}/telegram/accounts/{id}` | |

## Channels & Channel Sets

| Method | Path |
|---|---|
| GET / PATCH | `/workspaces/{ws}/channels[/{id}]` |
| GET / POST | `/workspaces/{ws}/channel-sets` |

## Content

| Method | Path | Notes |
|---|---|---|
| GET | `/workspaces/{ws}/content?status_filter=` | |
| GET | `/workspaces/{ws}/content/{id}` | |
| POST | `/workspaces/{ws}/content/generate` | the one AI call |
| PATCH | `/workspaces/{ws}/content/{id}` | manual edit |
| POST | `/workspaces/{ws}/content/{id}/submit` | → `PENDING_APPROVAL` |
| POST | `/workspaces/{ws}/content/{id}/approve` | → `APPROVED` |
| POST | `/workspaces/{ws}/content/{id}/reject` | → `REJECTED` |
| POST | `/workspaces/{ws}/content/{id}/schedule` | `{scheduled_at}`, also creates the `DistributionBatch` |

## Distributions

| Method | Path |
|---|---|
| GET | `/workspaces/{ws}/distributions?content_id=` |
| GET | `/workspaces/{ws}/distributions/{batch_id}` |
| POST | `/workspaces/{ws}/distributions/{batch_id}/retry-failed` |

## Media

| Method | Path |
|---|---|
| GET | `/workspaces/{ws}/media` |
| POST | `/workspaces/{ws}/media/upload` (multipart, 15 MB cap, magic-byte sniffing) |
| GET | `/workspaces/{ws}/media/{id}/content` (membership-checked byte stream from S3) |

## Settings / Analytics / Jobs / Autopilot / Sources

| Method | Path |
|---|---|
| GET | `/workspaces/{ws}/settings/ai-status` |
| GET | `/workspaces/{ws}/analytics/costs` |
| GET | `/workspaces/{ws}/analytics/content/{id}` |
| GET | `/workspaces/{ws}/jobs` |
| GET / PATCH | `/workspaces/{ws}/autopilot` |
| GET / POST | `/workspaces/{ws}/sources` |
| GET | `/workspaces/{ws}/ideas` |

## Realtime

`GET /ws/{workspace_id}` — WebSocket channel per workspace. The connection
manager (`main.py::ConnectionManager`) is wired up and ready for job/publish
status broadcasts; the publish/job services do not yet push events onto it
(tracked in ROADMAP.md) — today the Jobs page polls instead.

## Error shapes

- `403` — `PermissionDeniedError` (RBAC)
- `409` — `InvalidTransitionError` (content state machine)
- `402` — `BudgetExceededError`, body includes `{"kind": "daily"|"monthly"|"per_post"}`
- `415` — unsupported media upload
- `502` — AI generation failed after the one automatic retry
