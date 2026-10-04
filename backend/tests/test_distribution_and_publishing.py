import uuid

import pytest
from sqlalchemy import select

from app.models.content import ContentItem
from app.models.distribution import Publication
from app.models.enums import ChannelSetMode, ContentStatus, PublicationStatus, TelegramAccountStatus
from app.models.telegram import ChannelSet, ChannelSetMember, TelegramAccount, TelegramChannel
from app.services.publishing.distribution_service import DistributionService


async def _publications_of(db_session, batch_id):
    result = await db_session.execute(select(Publication).where(Publication.batch_id == batch_id))
    return list(result.scalars().all())


async def _make_channel_set_with_n_channels(db_session, n: int):
    from app.models.identity import Workspace

    ws_row = Workspace(name='W', slug=f'w-{uuid.uuid4().hex[:8]}')
    db_session.add(ws_row)
    await db_session.flush()
    workspace_id = ws_row.id
    account = TelegramAccount(
        workspace_id=workspace_id, phone_encrypted="enc", phone_masked="+1***67",
        status=TelegramAccountStatus.CONNECTED,
    )
    db_session.add(account)
    await db_session.flush()

    channel_set = ChannelSet(workspace_id=workspace_id, name="Talos Network", mode=ChannelSetMode.EXACT)
    db_session.add(channel_set)
    await db_session.flush()

    channels = []
    for i in range(n):
        channel = TelegramChannel(
            workspace_id=workspace_id, account_id=account.id, telegram_entity_id=1000 + i,
            title=f"Channel {i}", can_post=True,
        )
        db_session.add(channel)
        await db_session.flush()
        db_session.add(ChannelSetMember(channel_set_id=channel_set.id, channel_id=channel.id))
        channels.append(channel)
    await db_session.flush()

    item = ContentItem(
        workspace_id=workspace_id, status=ContentStatus.APPROVED, telegram_html="<b>Hello</b>",
        plain_text="Hello", channel_set_id=channel_set.id,
    )
    db_session.add(item)
    await db_session.flush()

    return workspace_id, channel_set, channels, item


@pytest.mark.asyncio
async def test_create_batch_fans_out_to_every_channel_with_unique_idempotency_keys(db_session):
    _, channel_set, channels, item = await _make_channel_set_with_n_channels(db_session, 10)
    service = DistributionService(db_session)

    batch = await service.create_batch(
        content_item=item, channel_set_id=channel_set.id, mode=ChannelSetMode.EXACT,
        workspace_cta_defaults={},
    )
    publications = await _publications_of(db_session, batch.id)

    assert len(publications) == 10
    channel_ids = {p.channel_id for p in publications}
    assert channel_ids == {c.id for c in channels}
    keys = {p.idempotency_key for p in publications}
    assert len(keys) == 10  # all unique
    assert all(p.status == PublicationStatus.PENDING for p in publications)


@pytest.mark.asyncio
async def test_batch_status_reflects_partial_failure(db_session):
    _, channel_set, channels, item = await _make_channel_set_with_n_channels(db_session, 10)
    service = DistributionService(db_session)
    batch = await service.create_batch(
        content_item=item, channel_set_id=channel_set.id, mode=ChannelSetMode.EXACT,
        workspace_cta_defaults={},
    )
    publications = await _publications_of(db_session, batch.id)

    for i, pub in enumerate(publications):
        pub.status = PublicationStatus.SUCCESS if i < 8 else PublicationStatus.FAILED
    await db_session.flush()

    status = await service.recompute_batch_status(batch)
    assert status.value == "PARTIAL_FAILURE"


@pytest.mark.asyncio
async def test_retry_failed_only_touches_failed_publications(db_session):
    from app.services.publishing.publishing_service import PublishingService

    _, channel_set, channels, item = await _make_channel_set_with_n_channels(db_session, 4)
    distribution_service = DistributionService(db_session)
    batch = await distribution_service.create_batch(
        content_item=item, channel_set_id=channel_set.id, mode=ChannelSetMode.EXACT,
        workspace_cta_defaults={},
    )
    pubs = await _publications_of(db_session, batch.id)

    pubs[0].status = PublicationStatus.SUCCESS
    pubs[1].status = PublicationStatus.SUCCESS
    pubs[2].status = PublicationStatus.FAILED
    pubs[3].status = PublicationStatus.FAILED
    await db_session.flush()

    publishing_service = PublishingService(db_session)
    retried_ids = await publishing_service.retry_failed(batch.id)

    assert set(retried_ids) == {pubs[2].id, pubs[3].id}
    await db_session.refresh(pubs[0])
    await db_session.refresh(pubs[2])
    assert pubs[0].status == PublicationStatus.SUCCESS  # untouched
    assert pubs[2].status == PublicationStatus.PENDING  # re-queued


@pytest.mark.asyncio
async def test_claim_is_idempotent_second_claim_returns_none(db_session):
    from app.services.publishing.publishing_service import PublishingService

    _, channel_set, channels, item = await _make_channel_set_with_n_channels(db_session, 1)
    distribution_service = DistributionService(db_session)
    batch = await distribution_service.create_batch(
        content_item=item, channel_set_id=channel_set.id, mode=ChannelSetMode.EXACT,
        workspace_cta_defaults={},
    )
    pubs = await _publications_of(db_session, batch.id)
    pub_id = pubs[0].id

    service = PublishingService(db_session)
    first_claim = await service.claim(pub_id)
    second_claim = await service.claim(pub_id)

    assert first_claim is not None
    assert second_claim is None  # already claimed -> no double-send
