from __future__ import annotations

import io

from PIL import Image
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession
from telethon.tl.types import Channel, InputPeerChannel

from app.core.config import get_settings
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


class TelethonTelegramProvider(TelegramProvider):
    def __init__(self):
        settings = get_settings()
        self._api_id = settings.telegram_api_id
        self._api_hash = settings.telegram_api_hash
        self._client: TelegramClient | None = None
        self._phone_code_hash: str | None = None

    async def _ensure_client(self, session_string: str = "") -> TelegramClient:
        if self._client is None:
            self._client = TelegramClient(
                StringSession(session_string), self._api_id, self._api_hash
            )
            await self._client.connect()
        return self._client

    async def send_code(self, phone: str) -> str:
        client = await self._ensure_client()
        try:
            sent = await client.send_code_request(phone)
        except FloodWaitError as exc:
            raise TelegramOperationError(
                "Flood wait while requesting code", TelegramErrorKind.FLOOD_WAIT, exc.seconds
            ) from exc
        except PhoneNumberInvalidError as exc:
            raise TelegramOperationError(
                "Telegram rejected this phone number.", TelegramErrorKind.AUTH_REQUIRED
            ) from exc
        self._phone_code_hash = sent.phone_code_hash
        return sent.phone_code_hash

    async def sign_in(self, phone: str, code: str, phone_code_hash: str) -> TelegramProfile:
        client = await self._ensure_client()
        try:
            user = await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError as exc:
            raise LoginRequires2FA() from exc
        except PhoneCodeInvalidError as exc:
            raise TelegramOperationError(
                "The verification code is invalid.", TelegramErrorKind.AUTH_REQUIRED
            ) from exc
        except PhoneCodeExpiredError as exc:
            raise TelegramOperationError(
                "The verification code has expired. Start again to get a new code.",
                TelegramErrorKind.AUTH_REQUIRED,
            ) from exc
        except FloodWaitError as exc:
            raise TelegramOperationError(
                "Too many attempts; Telegram asks to wait.", TelegramErrorKind.FLOOD_WAIT, exc.seconds
            ) from exc
        return TelegramProfile(
            telegram_user_id=user.id,
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            username=user.username,
            phone=phone,
        )

    async def sign_in_2fa(self, password: str) -> TelegramProfile:
        client = await self._ensure_client()
        try:
            user = await client.sign_in(password=password)
        except PasswordHashInvalidError as exc:
            raise TelegramOperationError(
                "The 2FA password is incorrect.", TelegramErrorKind.AUTH_REQUIRED
            ) from exc
        except FloodWaitError as exc:
            raise TelegramOperationError(
                "Too many attempts; Telegram asks to wait.", TelegramErrorKind.FLOOD_WAIT, exc.seconds
            ) from exc
        return TelegramProfile(
            telegram_user_id=user.id,
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            username=user.username,
            phone=user.phone or "",
        )

    async def export_session(self) -> str:
        client = await self._ensure_client()
        return client.session.save()

    async def restore_session(self, session_string: str) -> None:
        self._client = TelegramClient(
            StringSession(session_string), self._api_id, self._api_hash
        )
        await self._client.connect()

    async def list_administered_channels(self) -> list[TelegramDialog]:
        client = await self._ensure_client()
        dialogs = []
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if not isinstance(entity, Channel) or not entity.broadcast:
                continue
            can_post = bool(entity.creator or entity.admin_rights and entity.admin_rights.post_messages)
            dialogs.append(
                TelegramDialog(
                    telegram_entity_id=entity.id,
                    access_hash=entity.access_hash,
                    title=entity.title,
                    username=entity.username,
                    can_post=can_post,
                    subscriber_count=getattr(entity, "participants_count", None),
                )
            )
        return dialogs

    async def send_message(
        self, *, entity_id: int, access_hash: int | None, html: str, image_bytes: bytes | None
    ) -> SendMessageResult:
        client = await self._ensure_client()
        entity = await self._resolve(client, entity_id, access_hash)
        try:
            if image_bytes:
                image = io.BytesIO(image_bytes)
                # Telethon selects photo vs document by the stream's extension,
                # not its bytes. An unnamed BytesIO is sent as an "unnamed" document.
                with Image.open(image) as decoded:
                    if decoded.format in ("JPEG", "PNG"):
                        image.name = "post.jpg" if decoded.format == "JPEG" else "post.png"
                    else:
                        # WebP/GIF uploads are post illustrations too. Telegram
                        # photos use JPEG/PNG; publish their first frame as JPEG.
                        rgba = decoded.convert("RGBA")
                        photo = Image.new("RGB", rgba.size, "white")
                        photo.paste(rgba, mask=rgba.getchannel("A"))
                        image = io.BytesIO()
                        photo.save(image, format="JPEG", quality=95)
                        image.name = "post.jpg"
                image.seek(0)
                message = await client.send_file(
                    entity, image, caption=html, parse_mode="html", force_document=False
                )
            else:
                message = await client.send_message(entity, html, parse_mode="html")
        except FloodWaitError as exc:
            raise TelegramOperationError(
                "Flood wait while sending message", TelegramErrorKind.FLOOD_WAIT, exc.seconds
            ) from exc
        return SendMessageResult(telegram_message_id=message.id, telegram_channel_id=entity_id)

    async def get_message_metrics(
        self, *, entity_id: int, message_id: int, access_hash: int | None = None
    ) -> MessageMetrics:
        client = await self._ensure_client()
        entity = await self._resolve(client, entity_id, access_hash)
        messages = await client.get_messages(entity, ids=message_id)
        if not messages:
            return MessageMetrics()
        msg = messages
        reactions_count = 0
        if msg.reactions:
            reactions_count = sum(r.count for r in msg.reactions.results)
        return MessageMetrics(
            views=msg.views or 0,
            forwards=msg.forwards or 0,
            reactions=reactions_count,
            replies=(msg.replies.replies if msg.replies else 0),
        )

    async def read_channel_posts(self, *, username: str, limit: int = 30) -> list[ChannelPost]:
        client = await self._ensure_client()
        try:
            entity = await client.get_entity(username)
            messages = await client.get_messages(entity, limit=limit)
        except FloodWaitError as exc:
            raise TelegramOperationError("Flood wait while reading channel", TelegramErrorKind.FLOOD_WAIT, exc.seconds) from exc
        except (ValueError, TypeError) as exc:
            raise TelegramOperationError(f"Channel @{username} not found or not readable", TelegramErrorKind.ENTITY_NOT_FOUND) from exc
        return [ChannelPost(message_id=m.id, date=m.date, text=m.message or "") for m in messages if m.message]

    @staticmethod
    async def _resolve(client: TelegramClient, entity_id: int, access_hash: int | None):
        # A freshly restored StringSession has an empty entity cache, so a bare
        # integer id may not resolve. With the stored access_hash we can build
        # the input peer directly without a network lookup.
        if access_hash is not None:
            return InputPeerChannel(channel_id=entity_id, access_hash=access_hash)
        return await client.get_input_entity(entity_id)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.disconnect()
            self._client = None
