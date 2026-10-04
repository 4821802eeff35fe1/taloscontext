"""Regression tests for issues found in the post-implementation review."""
import uuid

import pytest
from sqlalchemy import select

from app.core.security import encrypt_session_string
from app.models.content import ContentItem
from app.models.distribution import Publication
from app.models.enums import (
    BatchStatus,
    ChannelSetMode,
    ContentStatus,
    PublicationStatus,
    TelegramAccountStatus,
)
from app.models.telegram import ChannelSet, ChannelSetMember, TelegramAccount, TelegramChannel
from app.services.publishing.distribution_service import DistributionService
from app.services.publishing.publishing_service import PublishingService
from app.services.telegram.account_service import TelegramAccountService


async def _setup(db_session, n=3, status=ContentStatus.PUBLISHING):
    ws = uuid.uuid4()
    account = TelegramAccount(
        workspace_id=ws, phone_encrypted="x", phone_masked="+1*",
        status=TelegramAccountStatus.CONNECTED,
        session_encrypted=encrypt_session_string("FAKE_SESSION_STRING_+1"),
    )
    db_session.add(account)
    await db_session.flush()
    cs = ChannelSet(workspace_id=ws, name="S", mode=ChannelSetMode.EXACT)
    db_session.add(cs)
    await db_session.flush()
    for i in range(n):
        ch = TelegramChannel(
            workspace_id=ws, account_id=account.id, telegram_entity_id=500 + i,
            access_hash=900 + i, title=f"C{i}", can_post=True,
        )
        db_session.add(ch)
        await db_session.flush()
        db_session.add(ChannelSetMember(channel_set_id=cs.id, channel_id=ch.id))
    item = ContentItem(workspace_id=ws, status=status, telegram_html="<b>x</b>", channel_set_id=cs.id)
    db_session.add(item)
    await db_session.flush()
    batch = await DistributionService(db_session).create_batch(
        content_item=item, channel_set_id=cs.id, mode=ChannelSetMode.EXACT, workspace_cta_defaults={}
    )
    pubs = list(
        (await db_session.execute(select(Publication).where(Publication.batch_id == batch.id))).scalars()
    )
    return ws, account, item, batch, pubs


@pytest.mark.asyncio
async def test_account_service_rejects_cross_workspace_access(db_session):
    _, account, *_ = await _setup(db_session)
    service = TelegramAccountService(db_session)
    with pytest.raises(ValueError):
        await service.disconnect(workspace_id=uuid.uuid4(), account_id=account.id)
    assert account.status == TelegramAccountStatus.CONNECTED


@pytest.mark.asyncio
async def test_batch_not_final_while_publications_pending(db_session):
    _, _, item, batch, pubs = await _setup(db_session)
    pubs[0].status = PublicationStatus.SUCCESS
    pubs[1].status = PublicationStatus.FAILED
    # pubs[2] still PENDING (e.g. waiting out a FloodWait)
    await db_session.flush()
    assert await DistributionService(db_session).recompute_batch_status(batch) == BatchStatus.PUBLISHING
    assert item.status == ContentStatus.PUBLISHING


@pytest.mark.asyncio
async def test_full_publish_through_fake_provider_marks_content_published(db_session):
    _, _, item, batch, pubs = await _setup(db_session, n=3)
    service = PublishingService(db_session)
    for p in pubs:
        await service.publish(p.id)
    for p in pubs:
        await db_session.refresh(p)
        assert p.status == PublicationStatus.SUCCESS
        assert p.telegram_message_id is not None
    await db_session.refresh(batch)
    assert batch.status == BatchStatus.SUCCESS
    assert item.status == ContentStatus.PUBLISHED
    assert item.published_at is not None

    # Re-running publish for an already-sent publication must not send again.
    before = pubs[0].telegram_message_id
    await service.publish(pubs[0].id)
    await db_session.refresh(pubs[0])
    assert pubs[0].telegram_message_id == before


@pytest.mark.asyncio
async def test_partial_failure_marks_content_partially_published(db_session):
    _, _, item, batch, pubs = await _setup(db_session, n=2)
    pubs[0].status = PublicationStatus.SUCCESS
    pubs[1].status = PublicationStatus.FAILED
    await db_session.flush()
    status = await DistributionService(db_session).recompute_batch_status(batch)
    assert status == BatchStatus.PARTIAL_FAILURE
    assert item.status == ContentStatus.PARTIALLY_PUBLISHED
