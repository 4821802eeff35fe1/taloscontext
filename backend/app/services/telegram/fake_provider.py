"""Deterministic fake Telegram provider — lets the full product flow (add
account -> login -> import channels -> create channel set -> publish) be
exercised in dev/tests without touching real Telegram or Telethon.

Like a real Telethon client, all login state lives in the exported session
string, so a fresh instance restored from it (e.g. in another API process or
after a restart) can continue the flow.

Magic values (dev/test only):
  code "22222"      -> account has Two-Step Verification, password required
  code "wrong"      -> invalid code
  password "wrong"  -> invalid 2FA password
Send failures can be injected per channel entity id through Redis
(see app/api/v1/dev.py), so E2E tests can exercise partial failure + retry.
"""
from __future__ import annotations

import hashlib
import json
import secrets

from app.services.telegram.base import (
    ChannelPost,
    LoginRequires2FA,
    MessageMetrics,
    SendMessageResult,
    TelegramDialog,
    TelegramErrorKind,
    TelegramOperationError,
    TelegramProfile,
    TelegramProvider,
)

_PREFIX = "FAKE_SESSION_STRING_"
FAIL_ENTITIES_KEY = "dev:fake_telegram:fail_entities"


def _user_id_for(phone: str) -> int:
    return 100_000_000 + int(hashlib.sha256(phone.encode()).hexdigest()[:7], 16)


class FakeTelegramProvider(TelegramProvider):
    def __init__(self) -> None:
        self._state: dict = {"phone": "", "authorized": False, "awaiting_password": False}

    def _profile(self) -> TelegramProfile:
        phone = self._state["phone"]
        return TelegramProfile(
            telegram_user_id=_user_id_for(phone),
            first_name="Fake",
            last_name="User",
            username=f"fake_{phone[-4:]}" if phone else "fake_user",
            phone=phone,
        )

    async def send_code(self, phone: str) -> str:
        self._state.update(phone=phone, authorized=False, awaiting_password=False)
        return "fake-hash-" + hashlib.sha256(phone.encode()).hexdigest()[:10]

    async def sign_in(self, phone: str, code: str, phone_code_hash: str) -> TelegramProfile:
        self._state["phone"] = phone
        if code == "wrong":
            raise TelegramOperationError("The verification code is invalid.", TelegramErrorKind.AUTH_REQUIRED)
        if code == "22222":
            self._state["awaiting_password"] = True
            raise LoginRequires2FA()
        self._state["authorized"] = True
        return self._profile()

    async def sign_in_2fa(self, password: str) -> TelegramProfile:
        if not self._state.get("awaiting_password"):
            raise TelegramOperationError("No password step in progress.", TelegramErrorKind.AUTH_REQUIRED)
        if password == "wrong":
            raise TelegramOperationError("The 2FA password is incorrect.", TelegramErrorKind.AUTH_REQUIRED)
        self._state.update(authorized=True, awaiting_password=False)
        return self._profile()

    async def export_session(self) -> str:
        return _PREFIX + json.dumps(self._state, separators=(",", ":"))

    async def restore_session(self, session_string: str) -> None:
        if not session_string.startswith(_PREFIX):
            raise TelegramOperationError("Session is not a fake-provider session.", TelegramErrorKind.AUTH_REQUIRED)
        raw = session_string[len(_PREFIX):]
        try:
            self._state = json.loads(raw)
        except json.JSONDecodeError:
            # v0.1 format: FAKE_SESSION_STRING_<phone>, always authorized
            self._state = {"phone": raw, "authorized": True, "awaiting_password": False}

    async def list_administered_channels(self) -> list[TelegramDialog]:
        return [
            TelegramDialog(
                telegram_entity_id=1000 + i,
                access_hash=5000 + i,
                title=f"Fake Channel {i}",
                username=f"fake_channel_{i}",
                can_post=True,
                subscriber_count=1200 * i,
            )
            for i in range(1, 6)
        ]

    async def send_message(
        self, *, entity_id: int, access_hash: int | None, html: str, image_bytes: bytes | None
    ) -> SendMessageResult:
        from app.core.redis import get_redis

        try:
            failing = await get_redis().sismember(FAIL_ENTITIES_KEY, str(entity_id))
        except Exception:  # noqa: BLE001  (no Redis in some unit tests)
            failing = False
        if failing:
            raise TelegramOperationError(
                "Injected fake failure: chat write forbidden.", TelegramErrorKind.NO_PERMISSION
            )
        return SendMessageResult(
            telegram_message_id=secrets.randbelow(2**31 - 1) + 1, telegram_channel_id=entity_id
        )

    async def get_message_metrics(
        self, *, entity_id: int, message_id: int, access_hash: int | None = None
    ) -> MessageMetrics:
        seed = (entity_id + message_id) % 500
        return MessageMetrics(views=seed * 10, forwards=seed // 10, reactions=seed // 5, replies=seed // 20)

    async def read_channel_posts(self, *, username: str, limit: int = 30) -> list[ChannelPost]:
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC).replace(microsecond=0)
        return [
            ChannelPost(message_id=500 - i, date=now - timedelta(hours=i),
                        text=f"Новость {i} из @{username}\nКороткое описание события номер {i}.")
            for i in range(min(limit, 3))
        ]

    async def disconnect(self) -> None:
        return None
