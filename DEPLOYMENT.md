# Deployment — v0.2.0

Compose provides PostgreSQL 16, Redis 7 with AOF, reference MinIO, API (two Uvicorn processes), worker, scheduler and static Nginx frontend. API migrations run before startup. Redis auth flows, queued messages and app events are shared across processes. Database rows are the source of truth for jobs/delivery.

```bash
cp .env.example .env
docker compose up -d --build
```

The example is a local fake-provider configuration. Set stable random signing/encryption keys before adding real accounts; production startup requires both. Set `APP_ENV=production`, HTTPS frontend/APP_URL/CORS, real credentials, supported S3 configuration and the appropriate fake flags. Real Timeweb Agent image generation remains unavailable. With Secure cookies enabled, plain HTTP will not support login.

Frontend proxies `/api/` on the same origin and serves SPA paths. SSE buffering is disabled. Docker DNS is re-resolved, so backend address changes on restart/recreation do not leave Nginx pointing at an old IP. If another proxy sits in front, configure trusted proxy count and network access restrictions accurately.

PostgreSQL/Redis/MinIO ports are bound to loopback; frontend is exposed on port 3000. Reference storage credentials are development defaults. Use deployment secrets and a maintained S3 provider/distribution for public production. Community MinIO is source-built at a pinned version because its former public image is not available in this environment; it is not a promise of current vendor security support.

`/health` checks API liveness. `/health/ready` reports PostgreSQL, Redis, S3, worker and scheduler heartbeats; readiness status requires PostgreSQL and Redis. Monitor worker/scheduler heartbeat fields separately. Configure process restart policies, TLS, access controls, logs/alerts and backups to match your infrastructure.

Scale API/worker after capacity tests. Scheduler replicas share an owned renewed Redis lease. A single backend service runs migrations at launch; for multiple independently deployed backend services, run migrations as a separate release step before scaling them.

Back up PostgreSQL, the media bucket and Redis (temporary flows/queue) appropriately. Preserve encryption keys with restricted access. Exercise restore procedures. Never use `docker compose down -v` on data you intend to keep. A crash during an external Telegram send can require manual delivery reconciliation; database/queue persistence cannot make that external transaction atomic.

See TESTING.md for the fake-provider Compose and restart acceptance procedure, and AUDIT.md for the checks actually completed.


## Installed server: context.talos.rest

Installed on 2026-10-05, Ubuntu 24.04 at 31.207.7.181, from tested release
commit `6370b4b`. This 1 GB RAM host uses native systemd services instead of
Docker; frontend was built locally with `VITE_API_BASE_URL=''` for same-origin API
requests. Later uncommitted frontend edits were preserved and not deployed.

- Source and Python environment: `/opt/channelos/backend` and its `.venv`.
- Static frontend: `/var/www/channelos`. Nginx vhost: `/etc/nginx/sites-available/channelos`.
- Secrets: `/etc/channelos/app.env`, root-only mode 0600. Never copy this file into Git.
- Services: `channelos-backend`, `channelos-worker`, `channelos-scheduler`, `channelos-minio`; all enabled and restarted automatically. Backend uses two API processes.
- PostgreSQL, Redis and MinIO bind to loopback. Redis has authentication and AOF; database and S3 credentials are randomly generated.
- Media: `/var/lib/channelos/media`. Database: PostgreSQL database `channelos`.
- Daily database/key backups: `/var/backups/channelos`, timer `channelos-backup.timer` at 03:15 UTC, retention seven days. These are local backups; media/off-server replication is not configured.
- Cloudflare serves public HTTPS. At the owner's request, no origin certificate was installed. Origin Nginx listens on HTTP port 80; Cloudflare must use an HTTP-compatible origin mode. Its trusted IP ranges are configured for client-IP rate limiting.
- Telegram and AI remain fake until real provider credentials are configured. Set the real API credentials and provider flags in the environment, then restart backend/worker/scheduler. A new user can create an account through the registration form.

Verified on this host: encrypted Telegram auth flow after backend restart, persisted
queued generation, scheduled fan-out to five fake publications, second restart with
unchanged message ids/attempts, MinIO upload/read, usage/cost and dashboard. All five
health checks passed. The origin login screen loaded in Chromium with no JavaScript
errors. Public-domain automated browser access stopped at Cloudflare's bot challenge;
a public authenticated session through Cloudflare was not verified. A separate test
workspace `1c126daf-e733-4cba-8776-608d0d02e0f5` holds the acceptance data.

Operations (on server):

```bash
systemctl status channelos-backend channelos-worker channelos-scheduler channelos-minio
journalctl -u channelos-backend -u channelos-worker -u channelos-scheduler -f
systemctl restart channelos-backend channelos-worker channelos-scheduler
systemctl start channelos-backup.service
curl http://127.0.0.1:8000/health/ready
```

Restart backend, worker and scheduler together because the background units depend
on the backend unit. Preserve the database, Redis files, media and environment keys
during updates. Capacity is suited to a small installation; load testing is pending.
