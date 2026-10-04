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
