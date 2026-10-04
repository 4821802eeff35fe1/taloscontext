"""P0.1: the Telegram login flow lives in Redis, not process memory."""
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.security import decrypt_session_string
from app.models.telegram import TelegramAccount, TelegramChannel
from app.services.telegram import factory as tg_factory
from app.services.telegram.auth_flow import AuthFlowError, AuthFlowState, TelegramAuthFlowService
from tests.conftest import register

PHONE = "+15551234567"


async def _new_service(db_session):
    """Simulates another API process / a restart: fresh service and provider
    instances, nothing shared but Redis and Postgres."""
    return TelegramAuthFlowService(db_session)


@pytest.mark.asyncio
async def test_flow_survives_restart_between_phone_and_code(db_session, redis_client, workspace, monkeypatch):
    created = []
    original = tg_factory.new_provider

    def tracking_provider():
        provider = original()
        created.append(provider)
        return provider

    monkeypatch.setattr("app.services.telegram.auth_flow.new_provider", tracking_provider)
    import uuid

    user_id = uuid.uuid4()
    flow = await (await _new_service(db_session)).start(workspace_id=workspace.id, user_id=user_id, phone=PHONE)
    assert flow["state"] == AuthFlowState.CODE_REQUIRED

    # "restart": a different service + provider instance continues from Redis only
    result = await (await _new_service(db_session)).submit_code(
        workspace_id=workspace.id, flow_id=flow["flow_id"], code="12345"
    )
    assert result["state"] == AuthFlowState.COMPLETED
    assert len(created) == 2 and created[0] is not created[1]

    account = (await db_session.execute(select(TelegramAccount))).scalar_one()
    assert account.workspace_id == workspace.id
    assert decrypt_session_string(account.session_encrypted).startswith("FAKE_SESSION_STRING_")
    assert PHONE not in account.phone_masked


@pytest.mark.asyncio
async def test_two_factor_flow_across_restarts(db_session, redis_client, workspace):
    import uuid

    flow = await TelegramAuthFlowService(db_session).start(workspace_id=workspace.id, user_id=uuid.uuid4(), phone=PHONE)
    flow = await TelegramAuthFlowService(db_session).submit_code(workspace_id=workspace.id, flow_id=flow["flow_id"], code="22222")
    assert flow["state"] == AuthFlowState.PASSWORD_REQUIRED
    flow = await TelegramAuthFlowService(db_session).submit_password(
        workspace_id=workspace.id, flow_id=flow["flow_id"], password="correct horse"
    )
    assert flow["state"] == AuthFlowState.COMPLETED


@pytest.mark.asyncio
async def test_redis_never_holds_code_password_or_plain_phone(db_session, redis_client, workspace):
    import uuid

    service = TelegramAuthFlowService(db_session)
    flow = await service.start(workspace_id=workspace.id, user_id=uuid.uuid4(), phone=PHONE)
    await service.submit_code(workspace_id=workspace.id, flow_id=flow["flow_id"], code="22222")
    raw_mid = await redis_client.get(f"tg_auth:{flow['flow_id']}")
    await service.submit_password(workspace_id=workspace.id, flow_id=flow["flow_id"], password="s3cr3t-pass")
    raw_done = await redis_client.get(f"tg_auth:{flow['flow_id']}")
    for raw in (raw_mid, raw_done):
        assert "22222" not in raw
        assert "s3cr3t-pass" not in raw
        assert PHONE not in raw
        assert "FAKE_SESSION_STRING" not in raw  # temporary session is encrypted
    done = json.loads(raw_done)
    assert "session_encrypted" not in done  # temp session deleted after completion


@pytest.mark.asyncio
async def test_wrong_code_keeps_flow_open_until_attempts_exhausted(db_session, redis_client, workspace):
    import uuid

    service = TelegramAuthFlowService(db_session)
    flow = await service.start(workspace_id=workspace.id, user_id=uuid.uuid4(), phone=PHONE)
    for i in range(4):
        flow = await service.submit_code(workspace_id=workspace.id, flow_id=flow["flow_id"], code="wrong")
        assert flow["state"] == AuthFlowState.CODE_REQUIRED, i
        assert "invalid" in flow["error"].lower()
    flow = await service.submit_code(workspace_id=workspace.id, flow_id=flow["flow_id"], code="wrong")
    assert flow["state"] == AuthFlowState.FAILED


@pytest.mark.asyncio
async def test_flow_is_scoped_to_its_workspace(db_session, redis_client, workspace):
    import uuid

    from app.models.identity import Workspace

    other = Workspace(name="Other", slug="other-ws")
    db_session.add(other)
    await db_session.flush()
    flow = await TelegramAuthFlowService(db_session).start(workspace_id=workspace.id, user_id=uuid.uuid4(), phone=PHONE)
    with pytest.raises(AuthFlowError) as exc:
        await TelegramAuthFlowService(db_session).submit_code(workspace_id=other.id, flow_id=flow["flow_id"], code="1")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_expired_flow_is_reported_and_refused(db_session, redis_client, workspace):
    import uuid

    service = TelegramAuthFlowService(db_session)
    flow = await service.start(workspace_id=workspace.id, user_id=uuid.uuid4(), phone=PHONE)
    raw = json.loads(await redis_client.get(f"tg_auth:{flow['flow_id']}"))
    raw["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    await redis_client.set(f"tg_auth:{flow['flow_id']}", json.dumps(raw), ex=300)
    assert (await service.get(workspace_id=workspace.id, flow_id=flow["flow_id"]))["state"] == AuthFlowState.EXPIRED
    with pytest.raises(AuthFlowError) as exc:
        await service.submit_code(workspace_id=workspace.id, flow_id=flow["flow_id"], code="12345")
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_concurrent_step_is_rejected(db_session, redis_client, workspace):
    import uuid

    service = TelegramAuthFlowService(db_session)
    flow = await service.start(workspace_id=workspace.id, user_id=uuid.uuid4(), phone=PHONE)
    await redis_client.set(f"tg_auth_lock:{flow['flow_id']}", "1", ex=60)  # another process is mid-step
    with pytest.raises(AuthFlowError) as exc:
        await service.submit_code(workspace_id=workspace.id, flow_id=flow["flow_id"], code="12345")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_api_flow_imports_channels_via_job(client, session_factory):
    ws = await register(client, "owner@example.com")
    r = await client.post(f"/api/v1/workspaces/{ws}/telegram/auth/start", json={"phone": PHONE})
    assert r.status_code == 201, r.text
    flow_id = r.json()["flow_id"]
    assert r.json()["state"] == "CODE_REQUIRED"

    r = await client.post(f"/api/v1/workspaces/{ws}/telegram/auth/{flow_id}/code", json={"code": "12345"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "COMPLETED" and body["refresh_job_id"]

    job = (await client.get(f"/api/v1/workspaces/{ws}/jobs/{body['refresh_job_id']}")).json()
    assert job["status"] == "SUCCESS" and job["job_type"] == "TELEGRAM_REFRESH_CHANNELS"
    async with session_factory() as s:
        assert len((await s.execute(select(TelegramChannel))).scalars().all()) == 5

    # Re-adding the same Telegram account updates it instead of duplicating.
    r = await client.post(f"/api/v1/workspaces/{ws}/telegram/auth/start", json={"phone": PHONE})
    await client.post(f"/api/v1/workspaces/{ws}/telegram/auth/{r.json()['flow_id']}/code", json={"code": "1"})
    accounts = (await client.get(f"/api/v1/workspaces/{ws}/telegram/accounts")).json()
    assert len(accounts) == 1 and accounts[0]["channel_count"] == 5
