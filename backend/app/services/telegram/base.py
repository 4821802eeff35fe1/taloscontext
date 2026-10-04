from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TelegramErrorKind(str, Enum):
    FLOOD_WAIT = "FLOOD_WAIT"
    NO_PERMISSION = "NO_PERMISSION"
    ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    NETWORK = "NETWORK"
    UNKNOWN = "UNKNOWN"


_DEFAULT_CODES = {
    "FLOOD_WAIT": "TELEGRAM_FLOOD_WAIT",
    "NO_PERMISSION": "NO_POST_PERMISSION",
    "ENTITY_NOT_FOUND": "TELEGRAM_ENTITY_NOT_FOUND",
    "AUTH_REQUIRED": "TELEGRAM_AUTH_REQUIRED",
    "NETWORK": "TELEGRAM_NETWORK_ERROR",
    "UNKNOWN": "TELEGRAM_ERROR",
}

# Specific, user-actionable login failures (localized by the UI).
_MESSAGE_CODES = {
    "verification code is invalid": "TELEGRAM_CODE_INVALID",
    "verification code has expired": "TELEGRAM_CODE_EXPIRED",
    "2fa password is incorrect": "TELEGRAM_PASSWORD_INVALID",
    "rejected this phone number": "TELEGRAM_PHONE_INVALID",
}


class TelegramOperationError(Exception):
    def __init__(self, message: str, kind: TelegramErrorKind, wait_seconds: int | None = None,
                 code: str | None = None):
        super().__init__(message)
        self.kind = kind
        self.wait_seconds = wait_seconds
        lowered = message.lower()
        self.code = code or next((c for k, c in _MESSAGE_CODES.items() if k in lowered), None) \
            or _DEFAULT_CODES.get(kind.value, "TELEGRAM_ERROR")


@dataclass
class TelegramProfile:
    telegram_user_id: int
    first_name: str
    last_name: str
    username: str | None
    phone: str


@dataclass
class TelegramDialog:
    telegram_entity_id: int
    access_hash: int | None
    title: str
    username: str | None
    can_post: bool
    subscriber_count: int | None


@dataclass
class SendMessageResult:
    telegram_message_id: int
    telegram_channel_id: int


@dataclass
class ChannelPost:
    message_id: int
    date: datetime | None
    text: str


@dataclass
class MessageMetrics:
    views: int = 0
    forwards: int = 0
    reactions: int = 0
    replies: int = 0


class LoginRequiresCode(Exception):
    def __init__(self, phone_code_hash: str):
        self.phone_code_hash = phone_code_hash


class LoginRequires2FA(Exception):
    pass


class TelegramProvider(ABC):
    """Wraps a single Telegram user account session (one instance per account)."""

    @abstractmethod
    async def send_code(self, phone: str) -> str:
        """Returns phone_code_hash."""

    @abstractmethod
    async def sign_in(self, phone: str, code: str, phone_code_hash: str) -> TelegramProfile:
        """Raises LoginRequires2FA if two-step verification is enabled."""

    @abstractmethod
    async def sign_in_2fa(self, password: str) -> TelegramProfile:
        ...

    @abstractmethod
    async def export_session(self) -> str:
        ...

    @abstractmethod
    async def restore_session(self, session_string: str) -> None:
        ...

    @abstractmethod
    async def list_administered_channels(self) -> list[TelegramDialog]:
        ...

    @abstractmethod
    async def send_message(
        self, *, entity_id: int, access_hash: int | None, html: str, image_bytes: bytes | None
    ) -> SendMessageResult:
        ...

    @abstractmethod
    async def get_message_metrics(
        self, *, entity_id: int, message_id: int, access_hash: int | None = None
    ) -> MessageMetrics:
        ...

    @abstractmethod
    async def read_channel_posts(self, *, username: str, limit: int = 30) -> list[ChannelPost]:
        """Recent posts of a channel the account can read (Telegram sources)."""

    @abstractmethod
    async def disconnect(self) -> None:
        ...
