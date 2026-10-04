"""Fake-only, destructive-to-own-test-data Compose restart acceptance check.
Run: backend/.venv/bin/python scripts/verify_compose.py
Use CHANNEL_OS_ENV_FILE to select the Compose env file (defaults to .env).
Creates a fresh test workspace, never deletes existing data.
"""
from __future__ import annotations

import asyncio
import base64
import os
import secrets
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("VERIFY_API_URL", "http://localhost:8000")
FRONTEND = os.environ.get("VERIFY_FRONTEND_URL", "http://localhost:3000")


async def compose(*args):
    result = await asyncio.to_thread(subprocess.run, ["docker", "compose", *args], cwd=ROOT, check=False,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout)


async def wait_for(fn, predicate=lambda value: bool(value), timeout=120):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            value = await fn()
            if predicate(value):
                return value
        except httpx.HTTPError:
            pass
        await asyncio.sleep(1)
    raise AssertionError("Timed out waiting for acceptance condition")


async def main():
    async with httpx.AsyncClient(base_url=BASE, headers={"X-ChannelOS-Client": "verification"},
                                 timeout=15, trust_env=False) as client:
        async def call(method, path, **kwargs):
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json() if response.status_code != 204 else None

        async def ready():
            response = await client.get("/health/ready")
            proxy = await client.get(FRONTEND + "/api/v1/auth/me")
            return response.status_code == 200 and proxy.status_code in (200, 401)

        await wait_for(ready)
        await call("POST", "/api/v1/auth/register", json={"email": f"restart-{secrets.token_hex(8)}@example.com",
                    "password": secrets.token_urlsafe(24), "workspace_name": "Compose restart acceptance"})
        ws = (await call("GET", "/api/v1/workspaces"))[0]["id"]
        prefix = f"/api/v1/workspaces/{ws}"
        status = await call("GET", prefix + "/settings/ai-status")
        assert status["telegram_provider_is_fake"] and status["text_provider_is_fake"], "Fake providers required"
        flow = await call("POST", prefix + "/telegram/auth/start", json={"phone": "+1555"+str(secrets.randbelow(9000000)+1000000)})
        await compose("restart", "backend")
        await wait_for(ready)
        restored = await call("POST", prefix + f"/telegram/auth/{flow['flow_id']}/code", json={"code": "00000"})
        assert restored["state"] == "COMPLETED"
        channels = await wait_for(lambda: call("GET", prefix + "/channels"), lambda rows: len(rows) == 5)
        target = await call("POST", prefix + "/channel-sets", json={"name": "Restart five", "channel_ids": [c["id"] for c in channels]})
        generated = await call("POST", prefix + "/content/generate", json={"instruction": "A practical post about CTR", "channel_set_id": target["id"]})
        content_id = generated["content"]["id"]
        await wait_for(lambda: call("GET", prefix + f"/content/{content_id}"), lambda row: row["status"] == "DRAFT")
        await call("POST", prefix + f"/content/{content_id}/submit")
        await call("POST", prefix + f"/content/{content_id}/approve")
        at = (datetime.now(UTC) + timedelta(seconds=45)).isoformat()
        await call("POST", prefix + f"/content/{content_id}/schedule", json={"scheduled_at": at})
        await compose("stop", "worker")
        queued = await call("POST", prefix + "/content/generate", json={"instruction": "A queued post survives restart", "channel_set_id": target["id"]})
        job_id = queued["job"]["id"]
        assert (await call("GET", prefix + f"/jobs/{job_id}"))["status"] == "QUEUED"
        await compose("restart", "backend", "worker", "scheduler")
        await wait_for(ready)
        await wait_for(lambda: call("GET", prefix + f"/jobs/{job_id}"), lambda row: row["status"] == "SUCCESS")
        await wait_for(lambda: call("GET", prefix + f"/content/{content_id}"), lambda row: row["status"] == "PUBLISHED")
        batches = await call("GET", prefix + f"/distributions?content_id={content_id}")
        pubs = batches[0]["publications"]
        assert len(batches) == 1 and len(pubs) == 5 and all(p["status"] == "SUCCESS" for p in pubs)
        before = {p["id"]: (p["telegram_message_id"], p["attempt"]) for p in pubs}
        await compose("restart", "backend", "worker", "scheduler")
        await wait_for(ready)
        await asyncio.sleep(17)  # at least one scheduler tick after restart
        after = (await call("GET", prefix + f"/distributions?content_id={content_id}"))[0]["publications"]
        assert {p["id"]: (p["telegram_message_id"], p["attempt"]) for p in after} == before
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jH1sAAAAASUVORK5CYII=")
        uploaded = await call("POST", prefix + "/media/upload", files={"file": ("test.png", png, "image/png")})
        image = await client.get(uploaded["url"])
        assert image.status_code == 200 and image.content
        costs = await call("GET", prefix + "/analytics/costs")
        assert float(costs["month_rub"]) > 0
        dashboard = await call("GET", prefix + "/analytics/dashboard")
        assert dashboard["posts_today"] == 1
        print("PASS: auth restart; persisted queued job; scheduled fan-out to 5; second restart without duplicate sends; MinIO upload/read; costs and dashboard")
        print(f"Acceptance workspace: {ws}")


if __name__ == "__main__":
    asyncio.run(main())
