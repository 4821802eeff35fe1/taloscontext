import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.content import ContentItem
from app.models.distribution import Publication
from app.models.enums import (
    ChannelSetMode,
    ContentStatus,
    PublicationStatus,
    TelegramAccountStatus,
)
from app.models.telegram import ChannelSet, ChannelSetMember, TelegramAccount, TelegramChannel
from app.services.publishing.distribution_service import DistributionService
from app.services.publishing.publishing_service import PublishingService
from app.services.telegram.base import TelegramErrorKind, TelegramOperationError


@pytest.mark.asyncio
async def test_flood_wait_sets_account_wait_window_and_keeps_publication_pending(db_session):
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

    channel = TelegramChannel(
        workspace_id=workspace_id, account_id=account.id, telegram_entity_id=42,
        title="Test channel", can_post=True,
    )
    db_session.add(channel)
    await db_session.flush()

    channel_set = ChannelSet(workspace_id=workspace_id, name="Set", mode=ChannelSetMode.EXACT)
    db_session.add(channel_set)
    await db_session.flush()
    db_session.add(ChannelSetMember(channel_set_id=channel_set.id, channel_id=channel.id))
    await db_session.flush()

    item = ContentItem(
        workspace_id=workspace_id, status=ContentStatus.APPROVED, telegram_html="<b>Hi</b>",
        plain_text="Hi", channel_set_id=channel_set.id,
    )
    db_session.add(item)
    await db_session.flush()

    distribution_service = DistributionService(db_session)
    batch = await distribution_service.create_batch(
        content_item=item, channel_set_id=channel_set.id, mode=ChannelSetMode.EXACT,
        workspace_cta_defaults={},
    )
    pub_result = await db_session.execute(select(Publication).where(Publication.batch_id == batch.id))
    publication = pub_result.scalars().first()

    publishing_service = PublishingService(db_session)
    exc = TelegramOperationError("Flood wait", TelegramErrorKind.FLOOD_WAIT, wait_seconds=68)
    await publishing_service._handle_failure(publication, account, exc)

    assert publication.status == PublicationStatus.PENDING  # retried, not terminally failed
    assert publication.flood_wait_seconds == 68
    assert account.status == TelegramAccountStatus.FLOOD_WAIT
    assert account.flood_wait_until > datetime.now(UTC)
    assert account.flood_wait_until <= datetime.now(UTC) + timedelta(seconds=70)
