# Telegram integration — v0.2.0

ChannelOS uses Telethon user accounts. Real credentials are `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` from my.telegram.org, plus a persistent Fernet session encryption key. Fake mode imports five channels and sends no real messages.

## Persistent login

`POST /api/v1/workspaces/{ws}/telegram/auth/start` creates a Redis flow. Submit `/auth/{flow}/code`, and `/auth/{flow}/password` if 2FA is required. `/auth/{flow}` exposes masked state and expiry. States are PHONE_SUBMITTED, CODE_REQUIRED, PASSWORD_REQUIRED, AUTHORIZING, COMPLETED, FAILED and EXPIRED.

Phone, phone-code hash and minimal serialized provider session are encrypted. Flow lifetime is ten minutes; a short tombstone permits an explicit expired response. Code/password are never stored. Each step restores a fresh provider from Redis and uses an owned renewed lock. On completion, the final session is committed to PostgreSQL before the Redis flow reports success. Channel import is a persisted job.

Backend restart between phone and code is verified with fake providers in both tests and the Docker restart acceptance script. Real Telethon login, 2FA and temporary StringSession restoration have not been exercised against Telegram in this build. If a process dies during AUTHORIZING, start a new flow after checking account state; the UI has no cross-tab auth-flow recovery list.

## Publishing

The provider restores the account's encrypted session, uses channel entity id/access hash, and sends text or media. An atomic Publication claim is persisted before the external send. Successful rows carry Telegram message ids. Failed rows have classified errors; FloodWait temporarily pauses the account and schedules retry. Successful publications are never included in retry-failed.

If delivery becomes uncertain, automatic retry is blocked. Content Studio exposes Confirm published / Confirm not delivered after a person checks the channel. Telegram and PostgreSQL cannot participate in one atomic transaction, so this design preserves uncertainty rather than claiming exactly-once delivery after every possible crash.

Metrics are views, forwards, reactions and replies when available from Telegram. They are snapshots, not fabricated growth estimates. Telegram permissions, rate limits, channel visibility and API availability determine what can be collected.

## Fake controls

Code `00000` completes login; `22222` requests 2FA; `wrong` simulates an invalid code/password. Fake channel failures can be configured using the development-only, role-protected endpoint `/workspaces/{ws}/dev/fake-telegram/failures`. Failure injection is scoped to the workspace and is not mounted in production.
