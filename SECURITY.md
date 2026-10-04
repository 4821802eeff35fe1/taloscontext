# Security

## Secrets

- `.env` is git-ignored; `.env.example` contains no real values.
- `Settings.validate_production()` (`core/config.py`) raises at startup if
  `APP_ENV=production` and `APP_SECRET_KEY` or
  `TELETHON_SESSION_ENCRYPTION_KEY` is unset — fail fast, not a silent
  insecure default.
- `structlog`'s `_redact_processor` (`core/logging.py`) replaces any log field
  named `password`, `code`, `session`/`session_string`, `token`, `api_key`,
  `secret`, `authorization`, `two_fa_password`, or `verification_code` with
  `***REDACTED***`, in addition to those values never being passed to log
  calls in application code in the first place.

## Telegram credentials

- StringSession is Fernet-encrypted before being written to Postgres
  (`core/security.py`); the raw session is only ever held in process memory
  during an active Telethon call. See `TELEGRAM.md` for the full flow and
  round-trip test.
- Phone numbers are stored encrypted and returned to the frontend only in
  masked form (`mask_phone`).
- Verification codes and 2FA passwords are never persisted anywhere, even
  transiently.

## Passwords and sessions

- User passwords are hashed with Argon2 (`argon2-cffi`), never stored or
  logged in plaintext.
- The web session is a signed, timed cookie (`itsdangerous`,
  `core/auth.py`) — `HttpOnly`, `SameSite=Lax`, `Secure` when
  `APP_ENV=production`. No session content beyond the user id is stored in
  the cookie, and the cookie cannot be decoded without `APP_SECRET_KEY`.

## Authorization (RBAC)

- Every mutating endpoint calls `require_role(member.role, MIN_ROLE)`
  server-side (`core/rbac.py`) before taking action — approving content needs
  at least `APPROVER`, managing Telegram accounts/settings needs `ADMIN`,
  managing members needs `OWNER`. The frontend's role-based UI hints are
  cosmetic only; every check that matters is re-done in the API layer
  (`tests/test_rbac.py`).
- Workspace membership is re-verified per request via `get_workspace_member`
  — a user can only act within workspaces they belong to.

## Upload handling

- `MediaService.upload` sniffs the actual file bytes (magic numbers) rather
  than trusting the client-supplied extension or `Content-Type`, rejects
  anything outside `{png, jpeg, webp, gif}`, and enforces a 15 MB cap
  (`services/media/service.py`).
- `sanitize_filename` strips path separators and non-word characters before
  any filename is used in a storage key.

## SSRF protection

- `services/security/ssrf_guard.py::assert_url_is_safe` resolves the
  hostname and blocks RFC1918 private ranges, loopback, link-local
  (including the `169.254.169.254` cloud metadata address), and their IPv6
  equivalents, before `SourceService` or any other outbound fetcher issues a
  request to a user- or AI-supplied URL.

## Telegram HTML sanitization

- `services/content/html_sanitizer.py::sanitize_telegram_html` strips any
  tag outside Telegram's supported set, drops anchors without a safe
  `http(s)://`/`tg://` href, and auto-closes unbalanced tags — applied to
  every AI-generated or manually-edited post **before** it's ever persisted,
  so a malformed tag can never reach `send_message` and trigger a Telegram
  parse error at publish time.

## Transport and CORS

- CORS origins are explicit (`Settings.cors_origins`), not a wildcard.
- All request handlers that touch the database operate within a single
  transaction (one `AsyncSession` per request, committed or rolled back as a
  unit) — no multi-request transactions, no partial writes left dangling on
  error.

## What is explicitly out of scope for this build

- Rate limiting / WAF at the HTTP edge — expected to be handled by a reverse
  proxy or platform-level gateway in front of the API, not reimplemented here.
- A dedicated secrets manager (Vault, etc.) — `.env` is adequate for the
  stated scope; swapping the config loader for one is a `core/config.py`
  change.
