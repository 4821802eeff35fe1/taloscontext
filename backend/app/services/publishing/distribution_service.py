from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.distribution import DistributionBatch, Publication
from app.models.enums import (
    CONTENT_TRANSITIONS,
    BatchStatus,
    ChannelSetMode,
    ContentStatus,
    PublicationStatus,
)
from app.models.telegram import ChannelSetMember, TelegramChannel
from app.services.content.cta_resolver import CTAResolverService


class DistributionService:
    """Fans a single ContentItem out to every channel in its target ChannelSet.

    AI is never called again here (mode EXACT/CTA_PER_CHANNEL/CONTACT_PER_CHANNEL):
    only ADAPTED is permitted to involve an extra AI call, and only when the
    channel set explicitly opts in — see product brief §7.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.cta_resolver = CTAResolverService()

    async def create_batch(
        self,
        *,
        content_item: ContentItem,
        channel_set_id: uuid.UUID,
        mode: ChannelSetMode,
        workspace_cta_defaults: dict[str, str],
    ) -> DistributionBatch:
        members_result = await self.session.execute(
            select(ChannelSetMember, TelegramChannel)
            .join(TelegramChannel, ChannelSetMember.channel_id == TelegramChannel.id)
            .where(ChannelSetMember.channel_set_id == channel_set_id)
        )
        rows = members_result.all()
        if not rows:
            raise ValueError("Channel set has no members")

        batch = DistributionBatch(
            workspace_id=content_item.workspace_id,
            content_item_id=content_item.id,
            channel_set_id=channel_set_id,
            status=BatchStatus.PENDING,
        )
        self.session.add(batch)
        await self.session.flush()

        for _, channel in rows:
            rendered_text = content_item.telegram_html
            resolved_cta = None

            if mode in (ChannelSetMode.CTA_PER_CHANNEL, ChannelSetMode.CONTACT_PER_CHANNEL):
                resolved_cta = self.cta_resolver.resolve(
                    cta_key=content_item.cta_key,
                    channel_cta_overrides_json=channel.cta_overrides_json,
                    workspace_cta_defaults=workspace_cta_defaults,
                )
                if resolved_cta:
                    rendered_text = f"{rendered_text}\n\n{resolved_cta}"
            elif mode == ChannelSetMode.EXACT:
                resolved_cta = self.cta_resolver.resolve(
                    cta_key=content_item.cta_key,
                    channel_cta_overrides_json="{}",
                    workspace_cta_defaults=workspace_cta_defaults,
                )
                if resolved_cta:
                    rendered_text = f"{rendered_text}\n\n{resolved_cta}"
            # ADAPTED mode's per-channel AI adaptation is handled by the caller
            # (ContentService) BEFORE calling this method, swapping rendered_text in.

            idempotency_key = hashlib.sha256(
                f"{batch.id}:{channel.id}".encode()
            ).hexdigest()

            self.session.add(
                Publication(
                    batch_id=batch.id,
                    channel_id=channel.id,
                    idempotency_key=idempotency_key,
                    status=PublicationStatus.PENDING,
                    rendered_text=rendered_text,
                    resolved_cta=resolved_cta,
                )
            )

        await self.session.flush()
        return batch

    async def recompute_batch_status(self, batch: DistributionBatch) -> BatchStatus:
        # Serialize aggregate updates after flushing this channel's outcome.
        # The last worker then sees every earlier committed result.
        await self.session.flush()
        await self.session.get(DistributionBatch, batch.id, with_for_update=True, populate_existing=True)
        result = await self.session.execute(
            select(Publication.status).where(Publication.batch_id == batch.id)
        )
        statuses = [row[0] for row in result.all()]
        terminal = {PublicationStatus.SUCCESS, PublicationStatus.FAILED}
        if any(s not in terminal for s in statuses):
            # Something is still pending/in flight — don't declare an outcome yet.
            batch.status = BatchStatus.PUBLISHING
        elif all(s == PublicationStatus.SUCCESS for s in statuses):
            batch.status = BatchStatus.SUCCESS
        elif all(s == PublicationStatus.FAILED for s in statuses):
            batch.status = BatchStatus.FAILED
        else:
            batch.status = BatchStatus.PARTIAL_FAILURE
        await self._sync_content_status(batch)
        await self.session.flush()
        return batch.status

    async def _sync_content_status(self, batch: DistributionBatch) -> None:
        """Mirrors a finished batch onto its ContentItem (PUBLISHED / PARTIALLY_PUBLISHED / FAILED)."""
        from datetime import UTC, datetime

        item = await self.session.get(ContentItem, batch.content_item_id)
        if item is None:
            return
        target = {
            BatchStatus.SUCCESS: ContentStatus.PUBLISHED,
            BatchStatus.PARTIAL_FAILURE: ContentStatus.PARTIALLY_PUBLISHED,
            BatchStatus.FAILED: ContentStatus.FAILED,
        }.get(batch.status)
        if target is None or item.status == target:
            return
        if target in CONTENT_TRANSITIONS.get(item.status, set()):
            item.status = target
            if target != ContentStatus.FAILED and item.published_at is None:
                item.published_at = datetime.now(UTC)

    async def prepare_batch(
        self, *, content_item: ContentItem, mode: ChannelSetMode, workspace_cta_defaults: dict[str, str]
    ) -> DistributionBatch:
        """Batch for (re)scheduling. A batch nothing has been sent from yet is
        rebuilt (picks up channel-set membership and text changes); a batch
        that already delivered somewhere is kept as is — never re-fanned out."""
        if content_item.channel_set_id is None:
            raise ValueError("Choose a target channel set before scheduling.")
        existing = (
            await self.session.execute(
                select(DistributionBatch).where(DistributionBatch.content_item_id == content_item.id)
            )
        ).scalars().all()
        for batch in existing:
            statuses = (
                await self.session.execute(select(Publication.status).where(Publication.batch_id == batch.id))
            ).scalars().all()
            if any(s != PublicationStatus.PENDING for s in statuses):
                return batch
            await self.session.delete(batch)
        await self.session.flush()
        return await self.create_batch(
            content_item=content_item,
            channel_set_id=content_item.channel_set_id,
            mode=mode,
            workspace_cta_defaults=workspace_cta_defaults,
        )
