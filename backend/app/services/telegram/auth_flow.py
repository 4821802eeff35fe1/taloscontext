"""Telegram login flow persisted in Redis.

phone -> code -> (2FA password) spans several HTTP requests that may land on
different API processes or straddle a restart, so nothing about the flow may
live in process memory. Between steps we keep, encrypted, only what Telethon
needs to continue: the temporary StringSession (holds the auth key the code
was sent for) and phone_code_hash. The verification code and the 2FA password
are used for one call and never stored anywhere.

The temporary session is deleted from Redis once the flow completes; the final
session is encrypted into telegram_accounts.session_encrypted as before.
"""
from __future__ import annotations

import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lease import lease
from app.core.redis import get_redis
from app.core.security import decrypt_session_string, encrypt_session_string, mask_phone
from app.models.enums import TelegramAccountStatus
from app.models.telegram import TelegramAccount
from app.services.telegram.base import LoginRequires2FA, TelegramOperationError, TelegramProfile
from app.services.telegram.factory import new_provider

FLOW_TTL_SECONDS = 600
# Keep the record a little past expiry so the UI can say "expired" instead of "not found".
TOMBSTONE_SECONDS = 300
MAX_CODE_ATTEMPTS = 5
MAX_PASSWORD_ATTEMPTS = 5


class AuthFlowState(str, Enum):
    PHONE_SUBMITTED = "PHONE_SUBMITTED"
    CODE_REQUIRED = "CODE_REQUIRED"
    PASSWORD_REQUIRED = "PASSWORD_REQUIRED"
    AUTHORIZING = "AUTHORIZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class AuthFlowError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "TELEGRAM_FLOW_INVALID"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _key(flow_id: str) -> str:
    return f"tg_auth:{flow_id}"


def _lock_key(flow_id: str) -> str:
    return f"tg_auth_lock:{flow_id}"


def public_view(flow: dict[str, Any]) -> dict[str, Any]:
    return {
        "flow_id": flow["flow_id"],
        "state": flow["state"],
        "phone_masked": flow["phone_masked"],
        "expires_at": flow["expires_at"],
        "error": flow.get("error"),
        "error_code": flow.get("error_code"),
        "wait_seconds": flow.get("wait_seconds"),
        "account_id": flow.get("result_account_id"),
        "attempts_left": (
            MAX_PASSWORD_ATTEMPTS - flow.get("password_attempts", 0)
            if flow["state"] == AuthFlowState.PASSWORD_REQUIRED
            else MAX_CODE_ATTEMPTS - flow.get("code_attempts", 0)
        ),
    }


class TelegramAuthFlowService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.redis = get_redis()

    async def _save(self, flow: dict[str, Any]) -> None:
        expires_at = datetime.fromisoformat(flow["expires_at"])
        ttl = max(1, int((expires_at - datetime.now(UTC)).total_seconds()) + TOMBSTONE_SECONDS)
        await self.redis.set(_key(flow["flow_id"]), json.dumps(flow), ex=ttl)

    async def get(self, *, workspace_id: uuid.UUID, flow_id: str) -> dict[str, Any]:
        raw = await self.redis.get(_key(flow_id))
        if raw is None:
            raise AuthFlowError("Login session not found or expired. Start again.", 404, "TELEGRAM_FLOW_NOT_FOUND")
        flow = json.loads(raw)
        if flow["workspace_id"] != str(workspace_id):
            # Same response as "missing" — don't confirm other tenants' flow ids.
            raise AuthFlowError("Login session not found or expired. Start again.", 404, "TELEGRAM_FLOW_NOT_FOUND")
        if flow["state"] not in (AuthFlowState.COMPLETED, AuthFlowState.FAILED) and (
            datetime.fromisoformat(flow["expires_at"]) <= datetime.now(UTC)
        ):
            flow["state"] = AuthFlowState.EXPIRED
            flow.pop("session_encrypted", None)
            flow.pop("phone_code_hash_encrypted", None)
        return flow

    async def start(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        phone: str,
        account_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        phone = phone.strip().replace(" ", "")
        if not phone.startswith("+") or not phone[1:].isdigit() or not 8 <= len(phone) <= 16:
            raise AuthFlowError("Enter the phone number in international format, e.g. +15551234567.", 422, "TELEGRAM_PHONE_INVALID")
        if account_id is not None:
            account = await self.session.get(TelegramAccount, account_id)
            if account is None or account.workspace_id != workspace_id:
                raise AuthFlowError("Telegram account not found", 404, "TELEGRAM_ACCOUNT_NOT_FOUND")

        now = datetime.now(UTC)
        flow: dict[str, Any] = {
            "flow_id": secrets.token_urlsafe(18),
            "workspace_id": str(workspace_id),
            "user_id": str(user_id),
            "account_id": str(account_id) if account_id else None,
            "phone_encrypted": encrypt_session_string(phone),
            "phone_masked": mask_phone(phone),
            "state": AuthFlowState.PHONE_SUBMITTED,
            "code_attempts": 0,
            "password_attempts": 0,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=FLOW_TTL_SECONDS)).isoformat(),
        }
        await self._save(flow)

        provider = new_provider()
        try:
            phone_code_hash = await provider.send_code(phone)
            flow["session_encrypted"] = encrypt_session_string(await provider.export_session())
            flow["phone_code_hash_encrypted"] = encrypt_session_string(phone_code_hash)
            flow["state"] = AuthFlowState.CODE_REQUIRED
        except TelegramOperationError as exc:
            flow["state"] = AuthFlowState.FAILED
            flow["error"] = str(exc)
            flow["error_code"] = exc.code
            flow["wait_seconds"] = exc.wait_seconds
        finally:
            await provider.disconnect()
        await self._save(flow)
        return flow

    async def submit_code(self, *, workspace_id: uuid.UUID, flow_id: str, code: str) -> dict[str, Any]:
        return await self._step(workspace_id, flow_id, AuthFlowState.CODE_REQUIRED, code=code)

    async def submit_password(self, *, workspace_id: uuid.UUID, flow_id: str, password: str) -> dict[str, Any]:
        return await self._step(workspace_id, flow_id, AuthFlowState.PASSWORD_REQUIRED, password=password)

    async def _step(
        self,
        workspace_id: uuid.UUID,
        flow_id: str,
        expected: AuthFlowState,
        *,
        code: str | None = None,
        password: str | None = None,
    ) -> dict[str, Any]:
        # One step at a time per flow, across all API processes.
        async with lease(self.redis, _lock_key(flow_id)) as acquired:
            if not acquired:
                raise AuthFlowError("This login step is already being processed.", 409, "TELEGRAM_FLOW_BUSY")
            flow = await self.get(workspace_id=workspace_id, flow_id=flow_id)
            if flow["state"] == AuthFlowState.EXPIRED:
                raise AuthFlowError("Login session expired. Start again to get a new code.", 410, "TELEGRAM_FLOW_EXPIRED")
            if flow["state"] != expected:
                raise AuthFlowError(f"Login is in state {flow['state']}, expected {expected.value}.", 409, "TELEGRAM_FLOW_STATE")

            flow["state"] = AuthFlowState.AUTHORIZING
            await self._save(flow)

            provider = new_provider()
            try:
                await provider.restore_session(decrypt_session_string(flow["session_encrypted"]))
                if code is not None:
                    flow["code_attempts"] += 1
                    profile = await provider.sign_in(
                        decrypt_session_string(flow["phone_encrypted"]),
                        code.strip(),
                        decrypt_session_string(flow["phone_code_hash_encrypted"]),
                    )
                else:
                    flow["password_attempts"] += 1
                    profile = await provider.sign_in_2fa(password or "")
                final_session = await provider.export_session()
            except LoginRequires2FA:
                flow["session_encrypted"] = encrypt_session_string(await provider.export_session())
                flow["state"] = AuthFlowState.PASSWORD_REQUIRED
                flow["error"] = flow["error_code"] = None
                await self._save(flow)
                return flow
            except TelegramOperationError as exc:
                attempts, limit = (
                    (flow["code_attempts"], MAX_CODE_ATTEMPTS)
                    if code is not None
                    else (flow["password_attempts"], MAX_PASSWORD_ATTEMPTS)
                )
                flow["error"] = str(exc)
                flow["error_code"] = exc.code
                flow["wait_seconds"] = exc.wait_seconds
                flow["state"] = AuthFlowState.FAILED if attempts >= limit else expected
                await self._save(flow)
                return flow
            finally:
                await provider.disconnect()

            account = await self._finalize(flow, profile, final_session)
            await self.session.commit()  # persist account before Redis declares completion
            flow["state"] = AuthFlowState.COMPLETED
            flow["error"] = flow["error_code"] = None
            flow["result_account_id"] = str(account.id)
            flow.pop("session_encrypted", None)
            flow.pop("phone_code_hash_encrypted", None)
            await self._save(flow)
            return flow

    async def _finalize(self, flow: dict[str, Any], profile: TelegramProfile, session_string: str) -> TelegramAccount:
        workspace_id = uuid.UUID(flow["workspace_id"])
        account: TelegramAccount | None = None
        if flow.get("account_id"):
            account = await self.session.get(TelegramAccount, uuid.UUID(flow["account_id"]))
        if account is None:
            # Re-adding an account already in this workspace updates it instead of duplicating.
            result = await self.session.execute(
                select(TelegramAccount).where(
                    TelegramAccount.workspace_id == workspace_id,
                    TelegramAccount.telegram_user_id == profile.telegram_user_id,
                )
            )
            account = result.scalar_one_or_none()
        if account is None:
            account = TelegramAccount(workspace_id=workspace_id)
            self.session.add(account)

        account.phone_encrypted = flow["phone_encrypted"]
        account.phone_masked = flow["phone_masked"]
        account.session_encrypted = encrypt_session_string(session_string)
        account.telegram_user_id = profile.telegram_user_id
        account.first_name = profile.first_name
        account.last_name = profile.last_name
        account.username = profile.username
        account.status = TelegramAccountStatus.CONNECTED
        account.flood_wait_until = None
        account.last_error = None
        account.last_heartbeat_at = datetime.now(UTC)
        await self.session.flush()
        return account
