from __future__ import annotations

import uuid
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_session_string, mask_phone
from app.models.enums import ChannelHealth, TelegramAccountStatus
from app.models.telegram import TelegramAccount, TelegramChannel
from app.services.telegram.base import LoginRequires2FA, TelegramOperationError
from app.services.telegram.factory import new_provider

# In-memory holder for in-progress login sessions, keyed by account id.
# A login flow is a short-lived, single-operator interaction; this is fine for
# a single-process API and avoids persisting half-authenticated Telethon state.
_PENDING_LOGINS: dict[uuid.UUID, dict] = {}


class TelegramAccountService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def start_login(self, *, workspace_id: uuid.UUID, phone: str) -> TelegramAccount:
        account = TelegramAccount(
            workspace_id=workspace_id,
            phone_encrypted=encrypt_session_string(phone),
            phone_masked=mask_phone(phone),
            status=TelegramAccountStatus.AUTH_REQUIRED,
        )
        self.session.add(account)
        await self.session.flush()

        provider = new_provider()
        phone_code_hash = await provider.send_code(phone)
        _PENDING_LOGINS[account.id] = {"provider": provider, "phone": phone, "hash": phone_code_hash}
        return account

    async def submit_code(self, *, workspace_id: uuid.UUID, account_id: uuid.UUID, code: str) -> TelegramAccount:
        account = await self._get(workspace_id, account_id)
        pending = _PENDING_LOGINS.get(account_id)
        if not pending:
            raise ValueError("No login in progress for this account")

        provider = pending["provider"]
        try:
            profile = await provider.sign_in(pending["phone"], code, pending["hash"])
        except LoginRequires2FA:
            account.status = TelegramAccountStatus.TWO_FA_REQUIRED
            await self.session.flush()
            return account
        except TelegramOperationError as exc:
            account.status = TelegramAccountStatus.ERROR
            account.last_error = str(exc)
            await self.session.flush()
            raise

        await self._finalize_login(account, provider, profile)
        return account

    async def submit_2fa(self, *, workspace_id: uuid.UUID, account_id: uuid.UUID, password: str) -> TelegramAccount:
        account = await self._get(workspace_id, account_id)
        pending = _PENDING_LOGINS.get(account_id)
        if not pending:
            raise ValueError("No login in progress for this account")

        provider = pending["provider"]
        profile = await provider.sign_in_2fa(password)
        await self._finalize_login(account, provider, profile)
        return account

    async def _finalize_login(self, account: TelegramAccount, provider, profile) -> None:
        from datetime import datetime

        session_string = await provider.export_session()
        account.session_encrypted = encrypt_session_string(session_string)
        account.telegram_user_id = profile.telegram_user_id
        account.first_name = profile.first_name
        account.last_name = profile.last_name
        account.username = profile.username
        account.status = TelegramAccountStatus.CONNECTED
        account.last_heartbeat_at = datetime.now(UTC)
        account.last_error = None
        await self.session.flush()
        _PENDING_LOGINS.pop(account.id, None)

    async def refresh_channels(self, *, workspace_id: uuid.UUID, account_id: uuid.UUID) -> list[TelegramChannel]:
        from app.core.security import decrypt_session_string

        account = await self._get(workspace_id, account_id)
        if not account.session_encrypted:
            raise ValueError("Account has no active session")

        provider = new_provider()
        try:
            await provider.restore_session(decrypt_session_string(account.session_encrypted))
            dialogs = await provider.list_administered_channels()
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

        from datetime import datetime

        account.last_heartbeat_at = datetime.now(UTC)
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
