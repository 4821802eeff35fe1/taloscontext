"""API contract the localized UI relies on: stable error codes with parameters,
a persisted per-user language, and notifications rendered from kind + metadata."""
import uuid

import pytest

from tests.conftest import register


@pytest.mark.asyncio
async def test_user_language_preference_round_trip(client):
    await register(client, "lang@example.com")
    me = (await client.get("/api/v1/auth/me")).json()
    assert me["language"] is None  # never chosen -> client decides (localStorage/browser)

    r = await client.patch("/api/v1/auth/me", json={"language": "ru"})
    assert r.status_code == 200 and r.json()["language"] == "ru"
    assert (await client.get("/api/v1/auth/me")).json()["language"] == "ru"

    # survives a new session
    await client.post("/api/v1/auth/logout")
    await client.post("/api/v1/auth/login", json={"email": "lang@example.com", "password": "supersecret123"})
    assert (await client.get("/api/v1/auth/me")).json()["language"] == "ru"

    assert (await client.patch("/api/v1/auth/me", json={"language": "de"})).status_code == 422
    # Fields not sent are not touched
    assert (await client.patch("/api/v1/auth/me", json={"full_name": "N"})).json()["language"] == "ru"
    assert (await client.patch("/api/v1/auth/me", json={"language": None})).json()["language"] is None


@pytest.mark.asyncio
async def test_register_stores_initial_language(client):
    r = await client.post("/api/v1/auth/register", json={
        "email": "ru@example.com", "password": "supersecret123", "workspace_name": "W", "language": "ru"})
    assert r.status_code == 201 and r.json()["language"] == "ru"


@pytest.mark.asyncio
async def test_error_responses_carry_codes_and_details(client):
    r = await client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"})
    assert r.status_code == 401 and r.json()["code"] == "AUTH_INVALID_CREDENTIALS" and r.json()["detail"]

    r = await client.get("/api/v1/auth/me")
    assert r.json()["code"] == "AUTH_REQUIRED"

    ws = await register(client, "codes@example.com")
    r = await client.get(f"/api/v1/workspaces/{uuid.uuid4()}/content")
    assert r.status_code == 404 and r.json()["code"] == "WORKSPACE_ACCESS_DENIED"
    r = await client.get(f"/api/v1/workspaces/{ws}/content/{uuid.uuid4()}")
    assert r.json()["code"] == "CONTENT_NOT_FOUND"

    r = await client.post(f"/api/v1/workspaces/{ws}/content/generate", json={})
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR" and isinstance(r.json()["detail"], list)

    del client.headers["X-ChannelOS-Client"]
    r = await client.post("/api/v1/auth/logout")
    assert r.json()["code"] == "CSRF_HEADER_MISSING"
    client.headers["X-ChannelOS-Client"] = "tests"


@pytest.mark.asyncio
async def test_budget_and_rate_limit_codes_have_parameters(client):
    ws = await register(client, "budget-code@example.com")
    base = f"/api/v1/workspaces/{ws}"
    await client.put(f"{base}/settings/budget", json={"daily_budget_rub": "0", "monthly_budget_rub": "100",
                                                     "max_cost_per_post_rub": "2", "budget_warning_pct": 80})
    r = await client.post(f"{base}/content/generate", json={"instruction": "x"})
    body = r.json()
    assert r.status_code == 402 and body["code"] == "BUDGET_EXCEEDED"
    assert body["details"]["kind"] == "daily" and "limit" in body["details"] and body["kind"] == "daily"

    for _ in range(5):
        await client.post("/api/v1/auth/login", json={"email": "z@example.com", "password": "bad"})
    r = await client.post("/api/v1/auth/login", json={"email": "z@example.com", "password": "bad"})
    assert r.status_code == 429 and r.json()["code"] == "AUTH_RATE_LIMITED"
    assert r.json()["details"]["retry_after"] > 0


@pytest.mark.asyncio
async def test_telegram_flow_errors_are_coded(client):
    ws = await register(client, "tg-code@example.com")
    base = f"/api/v1/workspaces/{ws}/telegram"
    r = await client.post(f"{base}/auth/start", json={"phone": "12345678"})
    assert r.status_code == 422 and r.json()["code"] == "TELEGRAM_PHONE_INVALID"
    flow = (await client.post(f"{base}/auth/start", json={"phone": "+15550007777"})).json()
    bad = (await client.post(f"{base}/auth/{flow['flow_id']}/code", json={"code": "wrong"})).json()
    assert bad["state"] == "CODE_REQUIRED" and bad["error_code"] == "TELEGRAM_CODE_INVALID"
    r = await client.get(f"{base}/auth/not-a-flow")
    assert r.status_code == 404 and r.json()["code"] == "TELEGRAM_FLOW_NOT_FOUND"


@pytest.mark.asyncio
async def test_notifications_include_render_parameters(client):
    ws = await register(client, "notif-meta@example.com")
    base = f"/api/v1/workspaces/{ws}"
    created = (await client.post(f"{base}/content", json={"title": "Weekly CTR", "telegram_html": "x"})).json()
    await client.post(f"{base}/content/{created['id']}/submit")
    item = (await client.get(f"{base}/notifications")).json()["items"][0]
    assert item["kind"] == "approval.required"
    assert item["metadata"]["title"] == "Weekly CTR" and item["metadata"]["content_id"] == created["id"]
