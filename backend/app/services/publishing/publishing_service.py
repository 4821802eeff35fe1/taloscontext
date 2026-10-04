from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_session_string
from app.models.distribution import DistributionBatch, Publication
from app.models.enums import PublicationStatus, TelegramAccountStatus
from app.models.media import MediaAsset
from app.models.telegram import TelegramAccount, TelegramChannel
from app.services.media.storage import MediaStorage
from app.services.publishing.distribution_service import DistributionService
from app.services.telegram.base import TelegramErrorKind, TelegramOperationError
from app.services.telegram.factory import new_provider


class PublicationAlreadyClaimedError(Exception):
    pass


class PublishingService:
    """Sends exactly one Publication. Idempotent: a Publication can only be
    claimed once from PENDING; a worker restart re-running this job for an
    already-SUCCESS row is a no-op (ARCHITECTURE.md §4 / §7).
    """

    def __init__(self, session: AsyncSession, media_storage: MediaStorage | None = None):
        self.session = session
        self.media_storage = media_storage
        self.distribution_service = DistributionService(session)

    async def claim(self, publication_id: uuid.UUID) -> Publication | None:
        result = await self.session.execute(
            update(Publication)
            .where(Publication.id == publication_id, Publication.status == PublicationStatus.PENDING)
            .values(status=PublicationStatus.CLAIMED)
            .returning(Publication)
        )
        row = result.first()
        await self.session.flush()
        if row is None:
            return None
        return row[0]

    async def publish(self, publication_id: uuid.UUID) -> Publication:
        publication = await self.claim(publication_id)
        if publication is None:
            existing = await self.session.get(Publication, publication_id)
            if existing is None:
                raise ValueError("Publication not found")
            return existing  # already claimed/sent — idempotent no-op

        publication.attempt += 1
        publication.status = PublicationStatus.SENDING
        await self.session.flush()

        channel = await self.session.get(TelegramChannel, publication.channel_id)
        account = await self.session.get(TelegramAccount, channel.account_id)

        if (
            account.status == TelegramAccountStatus.FLOOD_WAIT
            and account.flood_wait_until
            and account.flood_wait_until > datetime.now(UTC)
        ):
            publication.status = PublicationStatus.PENDING
            await self.session.flush()
            return publication  # scheduler will re-enqueue after wait expires

        if not channel.can_post:
            publication.status = PublicationStatus.FAILED
            publication.error_code = TelegramErrorKind.NO_PERMISSION.value
            publication.error_message = f"No permission to publish in @{channel.username or channel.title}"
            await self._finalize(publication)
            return publication

        image_bytes = await self._load_image(publication)

        provider = new_provider()
        try:
            await provider.restore_session(decrypt_session_string(account.session_encrypted))
            send_result = await provider.send_message(
                entity_id=channel.telegram_entity_id,
                access_hash=channel.access_hash,
                html=publication.rendered_text,
                image_bytes=image_bytes,
            )
        except TelegramOperationError as exc:
            await self._handle_failure(publication, account, exc)
            return publication
        finally:
            await provider.disconnect()

        publication.status = PublicationStatus.SUCCESS
        publication.telegram_message_id = send_result.telegram_message_id
        publication.telegram_channel_id = send_result.telegram_channel_id
        publication.published_at = datetime.now(UTC)
        account.last_heartbeat_at = publication.published_at
        if account.status == TelegramAccountStatus.FLOOD_WAIT:
            account.status = TelegramAccountStatus.CONNECTED
            account.flood_wait_until = None
        publication.error_code = None
        publication.error_message = None
        await self._finalize(publication)
        return publication

    async def _load_image(self, publication: Publication) -> bytes | None:
        from app.models.content import ContentItem

        batch = await self.session.get(DistributionBatch, publication.batch_id)
        content_item = await self.session.get(ContentItem, batch.content_item_id)
        if not content_item or not content_item.media_asset_id or not self.media_storage:
            return None
        asset = await self.session.get(MediaAsset, content_item.media_asset_id)
        if not asset:
            return None
        return await self.media_storage.get_object_bytes(asset.bucket, asset.object_key)

    async def _handle_failure(
        self, publication: Publication, account: TelegramAccount, exc: TelegramOperationError
    ) -> None:
        publication.error_code = exc.kind.value
        publication.error_message = str(exc)

        if exc.kind == TelegramErrorKind.FLOOD_WAIT:
            wait_seconds = exc.wait_seconds or 60
            publication.flood_wait_seconds = wait_seconds
            publication.status = PublicationStatus.PENDING  # retry after wait, not a terminal failure
            account.status = TelegramAccountStatus.FLOOD_WAIT
            account.flood_wait_until = datetime.now(UTC) + timedelta(seconds=wait_seconds)
        elif exc.kind in (TelegramErrorKind.NO_PERMISSION, TelegramErrorKind.ENTITY_NOT_FOUND):
            publication.status = PublicationStatus.FAILED
        elif exc.kind == TelegramErrorKind.AUTH_REQUIRED:
            publication.status = PublicationStatus.FAILED
            account.status = TelegramAccountStatus.AUTH_REQUIRED
        else:
            # NETWORK/UNKNOWN: eligible for exponential-backoff retry by the job system
            publication.status = PublicationStatus.FAILED if publication.attempt >= 5 else PublicationStatus.PENDING

        await self._finalize(publication)

    async def _finalize(self, publication: Publication) -> None:
        await self.session.flush()
        batch = await self.session.get(DistributionBatch, publication.batch_id)
        if batch:
            await self.distribution_service.recompute_batch_status(batch)

    async def retry_failed(self, batch_id: uuid.UUID) -> list[uuid.UUID]:
        """Re-queues only FAILED publications in a batch — succeeded ones are untouched."""
        result = await self.session.execute(
            select(Publication.id).where(
                Publication.batch_id == batch_id, Publication.status == PublicationStatus.FAILED
            )
        )
        ids = [row[0] for row in result.all()]
        await self.session.execute(
            update(Publication)
            .where(Publication.id.in_(ids))
            .values(status=PublicationStatus.PENDING)
        )
        await self.session.flush()
        return ids
