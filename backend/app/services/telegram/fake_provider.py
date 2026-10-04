"""Deterministic fake Telegram provider — lets the full product flow (add
account -> login -> import channels -> create channel set -> publish) be
exercised in dev/tests without touching real Telegram or Telethon.
"""
from __future__ import annotations

from app.services.telegram.base import (
    LoginRequires2FA,
    MessageMetrics,
    SendMessageResult,
    TelegramDialog,
    TelegramProfile,
    TelegramProvider,
)


class FakeTelegramProvider(TelegramProvider):
    def __init__(self, *, require_2fa: bool = False):
        self._require_2fa = require_2fa
        self._signed_in = False
        self._phone = ""
        self._message_counter = 1000

    async def send_code(self, phone: str) -> str:
        self._phone = phone
        return "fake-phone-code-hash"

    async def sign_in(self, phone: str, code: str, phone_code_hash: str) -> TelegramProfile:
        if code != "00000" and self._require_2fa:
            raise LoginRequires2FA()
        if code != "00000" and not self._require_2fa:
            # Any non-magic code still succeeds in fake mode for ease of testing,
            # except an explicit "wrong" sentinel.
            if code == "wrong":
                raise ValueError("Invalid code")
        self._signed_in = True
        return TelegramProfile(
            telegram_user_id=123456789,
            first_name="Fake",
            last_name="User",
            username="fake_user",
            phone=phone,
        )

    async def sign_in_2fa(self, password: str) -> TelegramProfile:
        if password == "wrong":
            raise ValueError("Invalid 2FA password")
        self._signed_in = True
        return TelegramProfile(
            telegram_user_id=123456789,
            first_name="Fake",
            last_name="User",
            username="fake_user",
            phone=self._phone,
        )

    async def export_session(self) -> str:
        return "FAKE_SESSION_STRING_" + self._phone

    async def restore_session(self, session_string: str) -> None:
        self._signed_in = session_string.startswith("FAKE_SESSION_STRING_")

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
        self._message_counter += 1
        return SendMessageResult(
            telegram_message_id=self._message_counter, telegram_channel_id=entity_id
        )

    async def get_message_metrics(
        self, *, entity_id: int, message_id: int, access_hash: int | None = None
    ) -> MessageMetrics:
        seed = (entity_id + message_id) % 500
        return MessageMetrics(views=seed * 10, forwards=seed // 10, reactions=seed // 5, replies=seed // 20)

    async def disconnect(self) -> None:
        self._signed_in = False
