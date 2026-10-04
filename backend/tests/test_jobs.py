"""P0.2: background work is persisted as Job rows and driven by the scheduler."""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.security import encrypt_session_string
from app.jobs import scheduler
from app.models.content import ContentItem
from app.models.distribution import Publication
from app.models.enums import (
    ChannelSetMode,
    ContentStatus,
    JobStatus,
    JobType,
    PublicationStatus,
    TelegramAccountStatus,
)
from app.models.ops import Job, JobAttempt
from app.models.telegram import ChannelSet, ChannelSetMember, TelegramAccount, TelegramChannel
from app.services.jobs.service import JobNotRetryableError, JobService
from app.services.publishing.distribution_service import DistributionService
from app.services.telegram.fake_provider import FAIL_ENTITIES_KEY


async def _publishing_item(session, workspace, n=3):
    account = TelegramAccount(
        workspace_id=workspace.id, phone_encrypted="x", phone_masked="+1*", status=TelegramAccountStatus.CONNECTED,
        session_encrypted=encrypt_session_string('FAKE_SESSION_STRING_{"phone":"+1","authorized":true}'),
    )
    session.add(account)
    await session.flush()
    cs = ChannelSet(workspace_id=workspace.id, name="Net", mode=ChannelSetMode.EXACT)
    session.add(cs)
    await session.flush()
    channels = []
    for i in range(n):
        ch = TelegramChannel(workspace_id=workspace.id, account_id=account.id, telegram_entity_id=7000 + i,
                             access_hash=1, title=f"C{i}", can_post=True)
        session.add(ch)
        await session.flush()
        session.add(ChannelSetMember(channel_set_id=cs.id, channel_id=ch.id))
        channels.append(ch)
    item = ContentItem(workspace_id=workspace.id, status=ContentStatus.SCHEDULED, telegram_html="<b>x</b>",
                       channel_set_id=cs.id, scheduled_at=datetime.now(UTC) - timedelta(seconds=5))
    session.add(item)
    await session.flush()
    await DistributionService(session).create_batch(content_item=item, channel_set_id=cs.id,
                                                    mode=ChannelSetMode.EXACT, workspace_cta_defaults={})
    await session.commit()
    return account, channels, item


async def _count(session, model, *where):
    return await session.scalar(select(func.count()).select_from(model).where(*where))


@pytest.mark.asyncio
async def test_scheduler_creates_one_job_per_publication_and_never_duplicates(
    session_factory, redis_client, inline_jobs, workspace, db_session
):
    await db_session.commit()
    account, channels, item = await _publishing_item(db_session, workspace)
    await scheduler.tick()
    async with session_factory() as s:
        jobs = (await s.execute(select(Job).where(Job.job_type == JobType.TELEGRAM_PUBLISH))).scalars().all()
        assert len(jobs) == 3
        assert all(j.status == JobStatus.SUCCESS and j.attempt == 1 for j in jobs)
        assert await _count(s, JobAttempt) == 3
        pubs = (await s.execute(select(Publication))).scalars().all()
        assert all(p.status == PublicationStatus.SUCCESS for p in pubs)
        assert (await s.get(ContentItem, item.id)).status == ContentStatus.PUBLISHED
    await scheduler.tick()
    await scheduler.tick()
    async with session_factory() as s:
        assert await _count(s, Job, Job.job_type == JobType.TELEGRAM_PUBLISH) == 3  # no duplicates


@pytest.mark.asyncio
async def test_injected_failure_marks_job_failed_with_error_code(
    session_factory, redis_client, inline_jobs, workspace, db_session
):
    await db_session.commit()
    _, channels, _ = await _publishing_item(db_session, workspace)
    await redis_client.sadd(FAIL_ENTITIES_KEY, str(channels[0].telegram_entity_id))
    await scheduler.tick()
    async with session_factory() as s:
        failed = (await s.execute(select(Job).where(Job.status == JobStatus.FAILED))).scalars().all()
        assert len(failed) == 1
        assert failed[0].error_code == "NO_PERMISSION"
        assert "Injected" in failed[0].error_message


@pytest.mark.asyncio
async def test_flood_wait_puts_job_in_retrying_and_scheduler_waits(
    session_factory, redis_client, inline_jobs, workspace, db_session, monkeypatch
):
    from app.services.telegram.base import TelegramErrorKind, TelegramOperationError
    from app.services.telegram.fake_provider import FakeTelegramProvider

    await db_session.commit()
    await _publishing_item(db_session, workspace, n=1)

    async def flood(self, **kwargs):
        raise TelegramOperationError("slow down", TelegramErrorKind.FLOOD_WAIT, wait_seconds=120)

    original_send = FakeTelegramProvider.send_message
    monkeypatch.setattr(FakeTelegramProvider, "send_message", flood)
    await scheduler.tick()
    async with session_factory() as s:
        job = (await s.execute(select(Job))).scalar_one()
        assert job.status == JobStatus.RETRYING
        assert job.error_code == "FLOOD_WAIT"
        assert scheduler._aware(job.next_retry_at) > datetime.now(UTC)
        pub = (await s.execute(select(Publication))).scalar_one()
        assert pub.status == PublicationStatus.PENDING and pub.flood_wait_seconds == 120
        assert pub.attempt == 0  # FloodWait is pacing, not a failed attempt

    monkeypatch.setattr(FakeTelegramProvider, "send_message", original_send)
    await scheduler.tick()  # still inside the wait window: nothing happens
    async with session_factory() as s:
        assert (await s.execute(select(Job))).scalar_one().status == JobStatus.RETRYING

    async with session_factory() as s:  # the FloodWait window passes
        past = datetime.now(UTC) - timedelta(seconds=1)
        (await s.execute(select(TelegramAccount))).scalar_one().flood_wait_until = past
        (await s.execute(select(Job))).scalar_one().next_retry_at = past
        await s.commit()
    await scheduler.tick()
    async with session_factory() as s:
        job = (await s.execute(select(Job))).scalar_one()
        assert job.status == JobStatus.SUCCESS and job.attempt == 2
        account = (await s.execute(select(TelegramAccount))).scalar_one()
        assert account.status == TelegramAccountStatus.CONNECTED


@pytest.mark.asyncio
async def test_retry_refused_when_publication_already_delivered(session_factory, redis_client, inline_jobs, workspace, db_session):
    await db_session.commit()
    await _publishing_item(db_session, workspace, n=1)
    await scheduler.tick()
    async with session_factory() as s:
        job = (await s.execute(select(Job))).scalar_one()
        job.status = JobStatus.FAILED  # pretend the job record says failed although the post went out
        await s.commit()
        with pytest.raises(JobNotRetryableError, match="only allowed for failed publications"):
            await JobService(s).retry(job)


@pytest.mark.asyncio
async def test_stale_running_job_is_recovered_and_unknown_delivery_not_resent(
    session_factory, redis_client, inline_jobs, workspace, db_session
):
    await db_session.commit()
    _, _, item = await _publishing_item(db_session, workspace, n=1)
    async with session_factory() as s:
        item = await s.get(ContentItem, item.id)
        item.status = ContentStatus.PUBLISHING
        pub = (await s.execute(select(Publication))).scalar_one()
        pub.status = PublicationStatus.SENDING  # worker died mid-send
        long_ago = datetime.now(UTC) - timedelta(hours=1)
        pub.updated_at = long_ago
        job = await JobService(s).create(workspace_id=workspace.id, job_type=JobType.TELEGRAM_PUBLISH,
                                         payload={"publication_id": str(pub.id)}, entity_type="publication",
                                         entity_id=pub.id)
        job.status, job.attempt, job.started_at = JobStatus.RUNNING, 1, long_ago
        await s.commit()

    await scheduler.tick()  # marks RETRYING (WORKER_LOST)
    await scheduler.tick(now=datetime.now(UTC) + timedelta(hours=1))  # retry runs the handler
    async with session_factory() as s:
        job = (await s.execute(select(Job))).scalar_one()
        assert job.status == JobStatus.FAILED and job.error_code == "DELIVERY_UNKNOWN"
        pub = (await s.execute(select(Publication))).scalar_one()
        assert pub.status == PublicationStatus.SENDING and pub.telegram_message_id is None  # not re-sent


@pytest.mark.asyncio
async def test_jobs_api_filters_search_cancel_and_retry(client, session_factory):
    from tests.conftest import register

    ws = await register(client, "jobs@example.com")
    async with session_factory() as s:
        service = JobService(s)
        a = await service.create(workspace_id=uuid.UUID(ws), job_type=JobType.SOURCE_FETCH, summary="Fetch Habr feed",
                                 payload={"source_id": str(uuid.uuid4())})
        b = await service.create(workspace_id=uuid.UUID(ws), job_type=JobType.AUTOPILOT_PLAN, summary="Plan")
        b.status, b.error_message, b.error_code = JobStatus.FAILED, "boom", "X"
        await s.commit()

    page = (await client.get(f"/api/v1/workspaces/{ws}/jobs", params={"q": "habr"})).json()
    assert [j["id"] for j in page["items"]] == [str(a.id)]
    page = (await client.get(f"/api/v1/workspaces/{ws}/jobs", params={"status": "FAILED"})).json()
    assert [j["id"] for j in page["items"]] == [str(b.id)]
    assert page["counts"]["QUEUED"] == 1 and page["counts"]["FAILED"] == 1

    r = await client.post(f"/api/v1/workspaces/{ws}/jobs/{a.id}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    r = await client.post(f"/api/v1/workspaces/{ws}/jobs/{a.id}/cancel")
    assert r.status_code == 409

    r = await client.post(f"/api/v1/workspaces/{ws}/jobs/{b.id}/retry")
    assert r.status_code == 200, r.text  # autopilot ran inline (no config -> success)
    detail = (await client.get(f"/api/v1/workspaces/{ws}/jobs/{b.id}")).json()
    assert detail["status"] == "SUCCESS" and len(detail["attempts"]) == 1


@pytest.mark.asyncio
async def test_jobs_pagination_cursor(client, session_factory):
    from tests.conftest import register

    ws = await register(client, "pages@example.com")
    async with session_factory() as s:
        for i in range(7):
            await JobService(s).create(workspace_id=uuid.UUID(ws), job_type=JobType.SOURCE_FETCH, summary=f"job {i}")
        await s.commit()
    seen, cursor = [], None
    while True:
        params = {"limit": 3, **({"cursor": cursor} if cursor else {})}
        page = (await client.get(f"/api/v1/workspaces/{ws}/jobs", params=params)).json()
        seen += [j["id"] for j in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(seen) == 7 and len(set(seen)) == 7
