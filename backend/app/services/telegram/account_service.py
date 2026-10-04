from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ChannelHealth, TelegramAccountStatus
from app.models.telegram import TelegramAccount, TelegramChannel
from app.services.telegram.base import TelegramErrorKind, TelegramOperationError
from app.services.telegram.factory import new_provider


class TelegramAccountService:
    """Operations on already-connected accounts. The login flow itself lives in
    auth_flow.py (Redis-backed, safe across processes and restarts)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def refresh_channels(self, *, workspace_id: uuid.UUID, account_id: uuid.UUID) -> list[TelegramChannel]:
        from app.core.security import decrypt_session_string

        account = await self._get(workspace_id, account_id)
        if not account.session_encrypted:
            raise ValueError("Account has no active session")

        provider = new_provider()
        try:
            await provider.restore_session(decrypt_session_string(account.session_encrypted))
            dialogs = await provider.list_administered_channels()
        except TelegramOperationError as exc:
            if exc.kind == TelegramErrorKind.AUTH_REQUIRED:
                account.status = TelegramAccountStatus.AUTH_REQUIRED
                account.last_error = "Telegram session is no longer valid. Reconnect the account."
                await self.session.flush()
            raise
        finally:
            await provider.disconnect()

        existing = await self.session.execute(
            select(TelegramChannel).where(TelegramChannel.account_id == account_id)
        )
        existing_by_entity = {c.telegram_entity_id: c for c in existing.scalars().all()}

        result_channels: list[TelegramChannel] = []
        for dialog in dialogs:
            channel = existing_by_entity.get(dialog.telegram_entity_id)
            if channel is None:
                channel = TelegramChannel(
                    workspace_id=account.workspace_id,
                    account_id=account.id,
                    telegram_entity_id=dialog.telegram_entity_id,
                )
                self.session.add(channel)
            channel.access_hash = dialog.access_hash
            channel.title = dialog.title
            channel.username = dialog.username
            channel.can_post = dialog.can_post
            channel.subscriber_count = dialog.subscriber_count
            channel.health = ChannelHealth.HEALTHY if dialog.can_post else ChannelHealth.NO_POST_PERMISSION
            result_channels.append(channel)

        # Channels the account no longer administers stay (history, sets) but can't receive posts.
        seen = {d.telegram_entity_id for d in dialogs}
        for entity_id, channel in existing_by_entity.items():
            if entity_id not in seen:
                channel.can_post = False
                channel.health = ChannelHealth.UNAVAILABLE

        account.last_heartbeat_at = datetime.now(UTC)
        if account.status in (TelegramAccountStatus.ERROR, TelegramAccountStatus.DISCONNECTED):
            account.status = TelegramAccountStatus.CONNECTED
        await self.session.flush()
        return result_channels

    async def disconnect(self, *, workspace_id: uuid.UUID, account_id: uuid.UUID) -> TelegramAccount:
        account = await self._get(workspace_id, account_id)
        account.status = TelegramAccountStatus.DISCONNECTED
        await self.session.flush()
        return account

    async def delete(self, *, workspace_id: uuid.UUID, account_id: uuid.UUID) -> None:
        account = await self._get(workspace_id, account_id)
        await self.session.delete(account)
        await self.session.flush()

    async def _get(self, workspace_id: uuid.UUID, account_id: uuid.UUID) -> TelegramAccount:
        account = await self.session.get(TelegramAccount, account_id)
        # Workspace check prevents acting on another tenant's account by guessing its id.
        if account is None or account.workspace_id != workspace_id:
            raise ValueError("Telegram account not found")
        return account
