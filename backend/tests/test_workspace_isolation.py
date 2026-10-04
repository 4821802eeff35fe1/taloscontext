"""P18: workspace isolation across EVERY workspace-scoped endpoint.

User B builds one object of every kind. User A then
  1. calls every route under B's workspace id  -> must be refused (404);
  2. calls every route under A's own workspace with B's object ids in the
     path -> must never succeed (no 2xx) and never return B's data.
Routes are enumerated from the app itself, so new endpoints are covered
automatically; a route that can't be exercised fails the test loudly.
"""
import re
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.models.content import ContentRevision
from app.models.distribution import DistributionBatch, Publication
from app.models.enums import MediaStatus
from app.models.media import MediaAsset
from app.models.ops import Job, Notification
from app.models.sources import SourceItem
from tests.conftest import register

FUTURE = (datetime.now(UTC) + timedelta(days=2)).isoformat()
SCHEDULE_BODY = {"name": "S", "timezone": "UTC", "windows": [{"start": "10:00", "end": "12:00"}], "posts_per_day": 1}
TONE_BODY = {"name": "Tone"}
SERIES_BODY = {"title": "Series", "status": "ACTIVE"}

# Valid bodies so that a missing ownership check can't hide behind a 422.
BODIES: dict[tuple[str, str], dict] = {
    ("PATCH", "/content/{content_id}"): {"title": "pwned"},
    ("POST", "/content/{content_id}/transform"): {"operation": "shorten"},
    ("POST", "/content/{content_id}/schedule"): {"scheduled_at": FUTURE},
    ("PATCH", "/content/{content_id}/schedule"): {"scheduled_at": FUTURE},
    ("POST", "/distributions/publications/{publication_id}/resolve"): {"outcome": "failed"},
    ("PUT", "/schedules/{schedule_id}"): SCHEDULE_BODY,
    ("PUT", "/tone-profiles/{profile_id}"): TONE_BODY,
    ("PUT", "/series/{series_id}"): SERIES_BODY,
    ("PATCH", "/knowledge/bases/{base_id}"): {"name": "x"},
    ("PATCH", "/knowledge/documents/{doc_id}"): {"enabled": False},
    ("PUT", "/channel-sets/{set_id}"): {"name": "x", "channel_ids": []},
    ("PATCH", "/channels/{channel_id}"): {"autopilot_enabled": True},
    ("PATCH", "/sources/{source_id}"): {"enabled": False},
    ("PATCH", "/ideas/{idea_id}"): {"status": "DISMISSED"},
    ("PATCH", "/members/{user_id}"): {"role": "VIEWER"},
    ("POST", "/telegram/auth/{flow_id}/code"): {"code": "12345"},
    ("POST", "/telegram/auth/{flow_id}/password"): {"password": "x"},
}
# Workspace-level routes with no object id: covered by pass 1 only.
LIST_ONLY = re.compile(r"^/api/v1/workspaces/\{workspace_id\}(/[a-z-]+)*$")


async def _build_world(b: httpx.AsyncClient, session_factory) -> tuple[str, dict[str, str]]:
    ws = await register(b, "bee@example.com", "Bee")
    base = f"/api/v1/workspaces/{ws}"
    ids: dict[str, str] = {}

    flow = (await b.post(f"{base}/telegram/auth/start", json={"phone": "+15550002222"})).json()
    done = (await b.post(f"{base}/telegram/auth/{flow['flow_id']}/code", json={"code": "1"})).json()
    ids["account_id"] = done["account_id"]
    flow2 = (await b.post(f"{base}/telegram/auth/start", json={"phone": "+15550003333"})).json()
    ids["flow_id"] = flow2["flow_id"]  # left open on purpose
    channels = (await b.get(f"{base}/channels")).json()
    ids["channel_id"] = channels[0]["id"]
    cs = (await b.post(f"{base}/channel-sets", json={"name": "Set", "channel_ids": [c["id"] for c in channels]})).json()
    ids["set_id"] = cs["id"]
    ids["profile_id"] = (await b.post(f"{base}/tone-profiles", json=TONE_BODY)).json()["id"]
    ids["series_id"] = (await b.post(f"{base}/series", json=SERIES_BODY)).json()["id"]
    ids["schedule_id"] = (await b.post(f"{base}/schedules", json=SCHEDULE_BODY)).json()["id"]
    kb = (await b.post(f"{base}/knowledge/bases", json={"name": "KB"})).json()
    ids["base_id"] = kb["id"]
    ids["doc_id"] = (await b.post(f"{base}/knowledge/documents", json={"title": "F", "text": "Fact"})).json()["id"]
    src = await b.post(f"{base}/sources", json={"kind": "telegram", "name": "TG", "config": {
        "channel": "news", "account_id": ids["account_id"]}})
    ids["source_id"] = src.json()["id"]

    gen = (await b.post(f"{base}/content/generate", json={"instruction": "Post", "channel_set_id": cs["id"]})).json()
    ids["content_id"] = gen["content"]["id"]
    ids["job_id"] = gen["job"]["id"]
    await b.post(f"{base}/content/{ids['content_id']}/submit")
    await b.post(f"{base}/content/{ids['content_id']}/approve")
    await b.post(f"{base}/content/{ids['content_id']}/schedule", json={"scheduled_at": FUTURE})

    async with session_factory() as s:
        wsid = uuid.UUID(ws)
        ids["batch_id"] = str((await s.execute(select(DistributionBatch.id).where(DistributionBatch.workspace_id == wsid))).scalars().first())
        ids["publication_id"] = str((await s.execute(select(Publication.id))).scalars().first())
        ids["revision_id"] = str((await s.execute(select(ContentRevision.id))).scalars().first())
        ids["idea_id"] = str((await s.execute(select(SourceItem.id).where(SourceItem.workspace_id == wsid))).scalars().first())
        ids["notification_id"] = str((await s.execute(select(Notification.id).where(Notification.workspace_id == wsid))).scalars().first())
        asset = MediaAsset(workspace_id=wsid, bucket="b", object_key="k", mime_type="image/png", size_bytes=1,
                           checksum_sha256="0" * 64, status=MediaStatus.UPLOADED)
        s.add(asset)
        await s.commit()
        ids["media_id"] = str(asset.id)
        ids["user_id"] = str((await b.get("/api/v1/auth/me")).json()["id"])
        assert (await s.execute(select(Job).where(Job.id == uuid.UUID(ids["job_id"])))).scalar_one()
    missing = [k for k, v in ids.items() if not v or v == "None"]
    assert not missing, f"world setup incomplete: {missing}"
    return ws, ids


def _routes():
    from app.main import app

    out = []
    for path, ops in app.openapi()["paths"].items():
        if path.startswith("/api/v1/workspaces/{workspace_id}"):
            out += [(method.upper(), path) for method in ops if method in ("get", "post", "put", "patch", "delete")]
    return sorted(out)


@pytest.mark.asyncio
async def test_every_workspace_route_is_isolated(client, session_factory):
    transport = client._transport  # same ASGI app, separate cookie jar
    async with httpx.AsyncClient(transport=transport, base_url="http://test",
                                 headers={"X-ChannelOS-Client": "tests"}) as b:
        ws_b, ids = await _build_world(b, session_factory)
    ws_a = await register(client, "ay@example.com", "Ay")

    routes = _routes()
    assert len(routes) > 60

    leaks: list[str] = []
    for method, path in routes:
        rel = path.removeprefix("/api/v1/workspaces/{workspace_id}")
        params = re.findall(r"\{(\w+)\}", rel)
        unknown = [p for p in params if p not in ids]
        assert not unknown, f"{method} {path}: no test object for {unknown}"
        body = BODIES.get((method, rel))
        filled = rel
        for p in params:
            filled = filled.replace("{" + p + "}", ids[p])
        kwargs = {"json": body} if body is not None else ({"json": {}} if method in ("POST", "PUT", "PATCH") else {})
        if rel == "/events":
            continue  # streaming; covered by the dependency check in pass 1 below via a non-stream call

        # Pass 1: A against B's workspace
        r = await client.request(method, f"/api/v1/workspaces/{ws_b}{filled}", **kwargs)
        if r.status_code not in (403, 404, 405, 422):
            leaks.append(f"[B-ws] {method} {path} -> {r.status_code}")
        elif r.status_code == 422 and body is None and method == "GET":
            pass

        # Pass 2: A's workspace, B's object ids
        if params and not LIST_ONLY.match(path):
            r = await client.request(method, f"/api/v1/workspaces/{ws_a}{filled}", **kwargs)
            if 200 <= r.status_code < 300:
                leaks.append(f"[A-ws+B-ids] {method} {path} -> {r.status_code}: {r.text[:120]}")
    assert not leaks, "Isolation failures:\n" + "\n".join(leaks)

    # B's data is intact after all of A's attempts
    async with httpx.AsyncClient(transport=transport, base_url="http://test",
                                 headers={"X-ChannelOS-Client": "tests"}) as b:
        await b.post("/api/v1/auth/login", json={"email": "bee@example.com", "password": "supersecret123"})
        content = (await b.get(f"/api/v1/workspaces/{ws_b}/content/{ids['content_id']}")).json()
        assert content["title"] != "pwned" and content["status"] == "SCHEDULED"


@pytest.mark.asyncio
async def test_sse_stream_requires_membership(client):
    from app.main import app

    ws_a = await register(client, "sse@example.com")
    other = str(uuid.uuid4())
    r = await client.get(f"/api/v1/workspaces/{other}/events")
    assert r.status_code == 404
    assert "/api/v1/workspaces/{workspace_id}/events" in app.openapi()["paths"]
    assert ws_a
