# Telegram integration

## Provider abstraction

`TelegramProvider` (`app/services/telegram/base.py`) is the only interface
services depend on. `TelethonTelegramProvider` wraps a single Telethon
`TelegramClient`; `FakeTelegramProvider` simulates the same contract
deterministically for dev/tests. `app/services/telegram/factory.py` picks
between them based on `USE_FAKE_TELEGRAM_PROVIDER`, and always returns a
**fresh instance** — one Telethon client per account/session, never shared
or cached across requests or across accounts.

## Login flow

```
POST /telegram/accounts/login        {phone}          -> send_code, status=AUTH_REQUIRED
POST /telegram/accounts/{id}/verify   {code}           -> sign_in
                                                          -> TWO_FA_REQUIRED if 2FA is on
POST /telegram/accounts/{id}/2fa      {password}       -> sign_in(password=...)
                                                          -> status=CONNECTED, session stored
```

`TelegramAccountService` holds the in-progress Telethon client + phone_code_hash
in an in-process dict keyed by account id for the duration of the login flow
(a human-paced, single-operator interaction) rather than persisting
half-authenticated state. Nothing from this flow is ever written to the
database except the final encrypted session string:

- the verification code is **never** persisted (not even transiently in the DB);
- the 2FA password is **never** persisted;
- the phone number is stored **encrypted** (`phone_encrypted`) and only a
  masked form (`phone_masked`, e.g. `+15*******67`) is ever returned by the API;
- the Telethon `StringSession` is encrypted with Fernet (derived from
  `TELETHON_SESSION_ENCRYPTION_KEY` via SHA-256) before it touches Postgres —
  see `core/security.py::encrypt_session_string` / `decrypt_session_string`,
  round-trip covered by `tests/test_security.py`.

## Channel import and permissions

`TelegramAccountService.refresh_channels` lists only broadcast channels the
account administers (`client.iter_dialogs()` filtered to `Channel` entities
with `broadcast=True`), and records `can_post` from the account's actual
admin rights (`creator` or `admin_rights.post_messages`) — the presence of a
channel in the list never implies posting permission. `health` is set to
`NO_POST_PERMISSION` when `can_post` is false, so the Channels UI can show an
honest state instead of letting a publish attempt fail downstream.

## Publishing and idempotency

`PublishingService.publish` atomically claims a `Publication` with
`UPDATE ... WHERE status='PENDING' RETURNING ...` before doing anything else
— a second call (e.g. a worker restart re-delivering the same job) sees no
row to claim and returns the already-claimed record untouched. See
`tests/test_distribution_and_publishing.py::test_claim_is_idempotent_...`.

A `DistributionBatch`'s publications are fully independent: 8 successes and
2 failures leave the batch `PARTIAL_FAILURE`, and `PublishingService.retry_failed`
re-queues **only** the `FAILED` rows — succeeded publications are never
touched again (`test_retry_failed_only_touches_failed_publications`).

## FloodWait and error classification

Telethon's `FloodWaitError` is translated into `TelegramOperationError(kind=FLOOD_WAIT,
wait_seconds=...)` at the provider boundary. `PublishingService._handle_failure`
then:

- sets the `Publication` back to `PENDING` (not `FAILED` — this is a retry,
  not a terminal failure);
- stores `flood_wait_seconds` on the publication for the UI;
- sets the owning `TelegramAccount.status = FLOOD_WAIT` and
  `flood_wait_until = now + wait_seconds`, so every other publication queued
  for that same account is skipped until the wait expires (checked at the top
  of `publish()`) instead of hammering Telegram again immediately.

Other Telegram RPC errors are classified into `NO_PERMISSION` /
`ENTITY_NOT_FOUND` (terminal failure, no retry), `AUTH_REQUIRED` (terminal,
flips the account to `AUTH_REQUIRED` for re-login), and `NETWORK`/`UNKNOWN`
(retried with a simple attempt cap, not an unbounded loop). Covered by
`tests/test_telegram_floodwait.py`.

## Metrics collection

`AnalyticsService.collect_metrics_for_publication` reads `views` / `forwards`
/ reaction counts / reply counts via `client.get_messages(...)` for a single
already-sent message and stores a `PostMetricSnapshot` — it only ever reads
Telegram's own reported counters, it never increments anything itself.
