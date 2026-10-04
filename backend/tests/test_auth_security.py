"""P0.3 rate limiting + server-side sessions + CSRF header."""
import pytest

from app.core.auth import SESSION_COOKIE_NAME
from tests.conftest import register


async def _login(client, email, password="supersecret123", ip=None):
    headers = {"X-Forwarded-For": ip} if ip else {}
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password}, headers=headers)


@pytest.mark.asyncio
async def test_login_rate_limited_per_ip_with_retry_after(client):
    await register(client, "a@example.com")
    for _ in range(5):
        r = await _login(client, "a@example.com", "wrong-password")
        assert r.status_code == 401
    r = await _login(client, "a@example.com", "wrong-password")
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
    # correct password is also refused while limited (no oracle)
    assert (await _login(client, "a@example.com")).status_code == 429


@pytest.mark.asyncio
async def test_unknown_and_known_email_get_identical_responses(client):
    await register(client, "known@example.com")
    known = await _login(client, "known@example.com", "wrong-password")
    unknown = await _login(client, "nobody@example.com", "wrong-password")
    assert known.status_code == unknown.status_code == 401
    assert known.json() == unknown.json()


@pytest.mark.asyncio
async def test_per_account_limit_applies_across_ips(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "trusted_proxy_count", 1)
    await register(client, "target@example.com")
    for i in range(10):
        r = await _login(client, "target@example.com", "nope", ip=f"10.0.0.{i}")
        assert r.status_code == 401, i
    r = await _login(client, "target@example.com", "nope", ip="10.0.0.99")
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_successful_login_resets_account_counter(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "trusted_proxy_count", 1)
    await register(client, "reset@example.com")
    for i in range(4):
        await _login(client, "reset@example.com", "nope", ip=f"10.1.0.{i}")
    assert (await _login(client, "reset@example.com", ip="10.1.1.1")).status_code == 200
    for i in range(9):
        assert (await _login(client, "reset@example.com", "nope", ip=f"10.2.0.{i}")).status_code == 401


@pytest.mark.asyncio
async def test_register_rate_limited(client):
    for i in range(5):
        r = await client.post("/api/v1/auth/register", json={
            "email": f"u{i}@example.com", "password": "supersecret123", "workspace_name": "W"})
        assert r.status_code == 201
    r = await client.post("/api/v1/auth/register", json={
        "email": "u9@example.com", "password": "supersecret123", "workspace_name": "W"})
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_telegram_code_submission_rate_limited(client):
    ws = await register(client, "tg@example.com")
    flow = (await client.post(f"/api/v1/workspaces/{ws}/telegram/auth/start", json={"phone": "+15550001111"})).json()
    for _ in range(4):
        r = await client.post(f"/api/v1/workspaces/{ws}/telegram/auth/{flow['flow_id']}/code", json={"code": "wrong"})
        assert r.status_code == 200
    # 5th wrong code fails the flow; further submissions hit the per-flow limit
    await client.post(f"/api/v1/workspaces/{ws}/telegram/auth/{flow['flow_id']}/code", json={"code": "wrong"})
    r = await client.post(f"/api/v1/workspaces/{ws}/telegram/auth/{flow['flow_id']}/code", json={"code": "12345"})
    assert r.status_code == 429 and "Retry-After" in r.headers


@pytest.mark.asyncio
async def test_new_session_id_on_every_login_and_logout_revokes(client):
    await register(client, "s@example.com")
    first = client.cookies.get(SESSION_COOKIE_NAME)
    assert (await _login(client, "s@example.com")).status_code == 200
    second = client.cookies.get(SESSION_COOKIE_NAME)
    assert first and second and first != second  # no session fixation

    stolen = second
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    client.cookies.set(SESSION_COOKIE_NAME, stolen)
    assert (await client.get("/api/v1/auth/me")).status_code == 401  # revoked server-side


@pytest.mark.asyncio
async def test_revoke_other_sessions(client):
    await register(client, "multi@example.com")
    other_device = client.cookies.get(SESSION_COOKIE_NAME)
    await _login(client, "multi@example.com")
    sessions = (await client.get("/api/v1/auth/sessions")).json()
    assert len(sessions) == 2 and sum(s["current"] for s in sessions) == 1
    assert (await client.post("/api/v1/auth/sessions/revoke-others")).status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    current = client.cookies.get(SESSION_COOKIE_NAME)
    client.cookies.set(SESSION_COOKIE_NAME, other_device)
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    client.cookies.set(SESSION_COOKIE_NAME, current)


@pytest.mark.asyncio
async def test_mutations_require_csrf_header(client):
    r = await client.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "x"},
                          headers={"X-ChannelOS-Client": ""})
    # header present (even empty) passes the guard; now drop it entirely
    del client.headers["X-ChannelOS-Client"]
    r = await client.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "x"})
    assert r.status_code == 403 and "X-ChannelOS-Client" in r.json()["detail"]
    assert (await client.get("/health")).status_code == 200  # safe methods unaffected
    client.headers["X-ChannelOS-Client"] = "tests"


@pytest.mark.asyncio
async def test_tampered_cookie_rejected(client):
    await register(client, "t@example.com")
    client.cookies.set(SESSION_COOKIE_NAME, client.cookies.get(SESSION_COOKIE_NAME)[:-2] + "xx")
    assert (await client.get("/api/v1/auth/me")).status_code == 401
