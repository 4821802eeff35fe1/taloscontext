from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_session_string
from app.models.analytics import PostMetricSnapshot
from app.models.distribution import Publication
from app.models.enums import PublicationStatus
from app.models.telegram import TelegramAccount, TelegramChannel
from app.services.telegram.factory import new_provider


class AnalyticsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def collect_metrics_for_publication(self, publication: Publication) -> PostMetricSnapshot | None:
        if publication.status != PublicationStatus.SUCCESS or not publication.telegram_message_id:
            return None

        channel = await self.session.get(TelegramChannel, publication.channel_id)
        account = await self.session.get(TelegramAccount, channel.account_id)
        provider = new_provider()
        try:
            await provider.restore_session(decrypt_session_string(account.session_encrypted))
            metrics = await provider.get_message_metrics(
                entity_id=channel.telegram_entity_id,
                message_id=publication.telegram_message_id,
                access_hash=channel.access_hash,
            )
        finally:
            await provider.disconnect()

        snapshot = PostMetricSnapshot(
            publication_id=publication.id,
            captured_at=datetime.now(UTC),
            views=metrics.views,
            forwards=metrics.forwards,
            reactions=metrics.reactions,
            replies=metrics.replies,
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def content_item_totals(self, content_item_id: uuid.UUID) -> dict:
        from app.models.distribution import DistributionBatch

        latest_per_pub = (
            select(
                PostMetricSnapshot.publication_id,
                func.max(PostMetricSnapshot.captured_at).label("latest"),
            )
            .group_by(PostMetricSnapshot.publication_id)
            .subquery()
        )

        result = await self.session.execute(
            select(
                Publication.channel_id,
                PostMetricSnapshot.views,
                PostMetricSnapshot.forwards,
                PostMetricSnapshot.reactions,
                Publication.published_at,
            )
            .join(DistributionBatch, Publication.batch_id == DistributionBatch.id)
            .join(
                latest_per_pub,
                latest_per_pub.c.publication_id == Publication.id,
            )
            .join(
                PostMetricSnapshot,
                (PostMetricSnapshot.publication_id == Publication.id)
                & (PostMetricSnapshot.captured_at == latest_per_pub.c.latest),
            )
            .where(DistributionBatch.content_item_id == content_item_id)
        )
        rows = result.all()
        total_views = sum(r.views for r in rows)
        total_forwards = sum(r.forwards for r in rows)
        total_reactions = sum(r.reactions for r in rows)
        return {
            "total_views": total_views,
            "total_forwards": total_forwards,
            "total_reactions": total_reactions,
            "per_channel": [
                {
                    "channel_id": str(r.channel_id),
                    "views": r.views,
                    "forwards": r.forwards,
                    "reactions": r.reactions,
                    "published_at": r.published_at,
                }
                for r in rows
            ],
        }
