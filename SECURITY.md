# Security — v0.2.0

## Authentication and isolation

Passwords use Argon2. An HttpOnly, SameSite=Lax cookie contains a signed server-side session **id**; signing does not encrypt the cookie. PostgreSQL session rows support expiry, idle timeout, logout and revocation of other sessions. Login rotates the session id. Production cookies are Secure.

Workspace endpoints check membership and role server-side. The HTTP isolation suite enumerates workspace routes from OpenAPI and exercises both another workspace's path and foreign entity ids in an owned workspace. This complements role, reference and revocation tests; UI controls are not authorization boundaries.

State-changing API calls require `X-ChannelOS-Client`. CORS permits configured origins only. Redis limits registration, login by IP/email, Telegram code and password attempts, returning 429 and Retry-After. Unknown-email login does the same password-hash work and uses the same invalid-credentials response.

`TRUSTED_PROXY_COUNT` defaults to 0. Set it to the exact trusted proxy count for your deployment; restrict direct API access when enabling it.

## Telegram secrets

Temporary Telegram auth flows have a ten-minute lifetime in Redis, with encrypted phone, phone-code hash and serialized session. Verification codes and 2FA passwords are used in memory for one request and never persisted. Completed StringSession values are Fernet-encrypted in PostgreSQL. Redis and database backups contain sensitive encrypted material and require access control.

Production startup requires a signing key and Telegram session encryption key. Keep keys stable across restarts and store them outside Git. Settings returns masked credentials/configuration flags. Audit metadata recursively redacts sensitive keys; application logging redacts named sensitive fields. Exception messages and third-party provider responses must not be treated as safe secret containers.

## Sources and uploads

Source URLs must use HTTP(S), contain no embedded credentials, and resolve entirely to public unicast addresses. Private, loopback, link-local, unspecified, multicast, CGNAT and IPv4-mapped private addresses are refused. Each redirect is checked. Fetches connect to the validated IP while retaining HTTP Host and TLS SNI, preventing a second DNS resolution from rebinding the request. Environment proxies are disabled for these requests. Size, redirect and timeout limits apply.

Media uploads are read with a byte limit and validated by content. Object keys are generated from workspace id and checksum, not user paths. Downloads require workspace membership. Knowledge supports bounded TXT/MD/JSON/CSV/PDF parsing; malformed imports are rejected. Telegram export metadata is retained.

Telegram HTML uses an allow-list on the server and in browser preview. Editor-to-Telegram conversion drops unsafe tags/URLs. Backend media responses set nosniff and a restrictive sandbox CSP.

## Concurrency and delivery

Owned Redis leases renew scheduler/auth locks and cancel work if ownership is lost. PostgreSQL locks serialize content modifications, series assignment, job claim, batch aggregation and workspace AI budget checks. Publication claims are committed before Telegram sends. A crash during a send leaves uncertain delivery for manual resolution, never an automatic resend. This is not a claim of distributed exactly-once delivery.

SSE rechecks session validity and workspace membership and releases the request DB connection before streaming. Redis pub/sub has no replay log; clients refetch on reconnect.

## Dependency review

Vite/Vitest were upgraded after the dependency audit. `npm audit --omit=dev` is the production dependency check. Tailwind 3's build-time `braces` dependency has an [unpatched recursion denial-of-service advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm); only trusted repository content/globs may enter the build. It is absent from the static Nginx runtime. Migration to Tailwind 4 remains follow-up work.

The bundled community MinIO is a pinned source build for local/reference deployment. Before public production use, choose supported S3 storage or a maintained MinIO distribution and review its security updates. HTTPS, backups, secret rotation, observability, restricted registration and infrastructure access controls belong to the deployment configuration. No penetration test or large-scale load test is claimed.
