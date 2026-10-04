# Testing

## Backend

```bash
cd backend && source .venv/bin/activate
pytest -q
```

45 tests, all passing, zero network calls, zero real cost — `tests/conftest.py`
forces `USE_FAKE_*=true` and an in-memory SQLite database before any app
module is imported.

| File | Covers |
|---|---|
| `test_security.py` | Telethon session encrypt/decrypt round-trip, password hashing, phone masking |
| `test_costs.py` | `compute_cost` formula, budget guard (daily/monthly/per-post), AIRequest/CostEvent persistence |
| `test_duplicate_detection.py` | identical vs. unrelated text scoring, empty-history edge case |
| `test_cta_resolver.py` | channel override vs. workspace default precedence, unknown-key fallback |
| `test_schedule_service.py` | timezone-aware window expansion, excluded weekdays, min-interval enforcement across windows |
| `test_content_state_machine.py` | every `CONTENT_TRANSITIONS` edge used by the API, including terminal `ARCHIVED` |
| `test_html_sanitizer.py` | allowed tags pass through, disallowed tags stripped, unclosed tags auto-closed, unsafe `href` dropped |
| `test_ssrf_guard.py` | private/link-local/metadata IPs blocked, non-http schemes blocked |
| `test_ai_service.py` | one `FakeAIProvider` call produces a valid `GenerationResult` and exactly one `AIRequest` row |
| `test_distribution_and_publishing.py` | fan-out to every channel with unique idempotency keys, partial-failure batch status, retry touches only failed publications, double-claim is a no-op |
| `test_telegram_floodwait.py` | FloodWait sets account `flood_wait_until` and keeps the publication `PENDING` (not `FAILED`) |
| `test_rbac.py` | role-rank checks for every `CAN_*` constant |
| `test_review_fixes.py` | cross-workspace account access rejected; batch not finalized while publications are in flight; full send of every publication through `PublishingService` + `FakeTelegramProvider` → batch `SUCCESS`, content `PUBLISHED`, re-run sends nothing; partial failure → content `PARTIALLY_PUBLISHED` |
| `test_knowledge_service.py` | Telegram JSON export importer extracts message text (including entity-array text) and chunks it |

Linting: `ruff check app` — 1 remaining style notice (nested `if` in the fake Telegram provider).
unpack vars, a `zip`→`itertools.pairwise` suggestion, `try/except/pass`
without logging in two non-critical health-check branches, ARQ's required
mutable class attribute on `WorkerSettings`; none affect correctness).

## Frontend

```bash
cd frontend
npx tsc -b        # strict typecheck, passes clean
npm run build     # tsc -b && vite build — production bundle, passes clean
```

No Vitest/RTL component tests were written in this pass — the frontend's
correctness was instead verified by running the actual dev server against
the actual backend (see below) and exercising every page manually. Adding
component tests for the generate/approve/schedule flow is the natural next
step (ROADMAP.md).

## What was run live during development (no Docker/Postgres/Redis available
## in this sandbox — see AUDIT.md for the full explanation)

1. `uvicorn app.main:app` against a fresh SQLite database with
   `alembic upgrade head` applied.
2. `npm run dev` for the frontend; confirmed it serves and the dev server
   boots clean.
3. A full curl-driven run of the real product flow against the running
   backend: register → login → start Telegram login → submit code
   (`FakeTelegramProvider`) → import 5 channels → create a Channel Set →
   generate one post (`FakeAIProvider`) → verify cost ledger incremented by
   exactly one AI call's cost → submit for approval → approve → schedule.
   Inspecting the SQLite file directly afterward confirmed **one**
   `ContentItem`, **one** `DistributionBatch`, and **five** `Publication`
   rows with five distinct `idempotency_key`s — the core architectural claim
   of the whole project, verified against running code, not just unit tests.
4. `alembic revision --autogenerate` against a real (SQLite, for lack of a
   local Postgres) database produced all 30 tables with zero manual
   corrections needed, and `alembic upgrade head` applied them cleanly.

## What was not run live

- Real Telethon calls against real Telegram (`TELEGRAM_API_ID`/`HASH` were
  never populated with real credentials in this environment).
- Real Timeweb Agent calls (`TIMEWEB_AGENT_API_KEY` was never populated).
- The ARQ worker and standalone scheduler process against a real Redis — no
  Redis server was available in this sandbox without an elevated-permission
  `brew install` this session chose not to perform unilaterally. Their logic
  (claim/idempotency/retry/FloodWait/batch status) is covered by the unit
  tests above, which exercise the exact same service code the worker calls.
- Playwright E2E and Vitest component tests — not written in this pass.

Do not take "tested" to mean "tested against real Telegram/Timeweb traffic"
anywhere in this document — it specifically means run against the fake
providers plus the unit suite above, as detailed per item.
