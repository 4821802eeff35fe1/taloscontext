"""Exercise Telethon's real media selection without connecting to Telegram."""

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import InputFile, InputMediaUploadedPhoto, InputPeerChannel

from app.services.telegram.telethon_provider import TelethonTelegramProvider


@pytest.mark.parametrize("image_format", ["JPEG", "PNG", "WEBP", "GIF"])
async def test_post_image_is_uploaded_as_photo(image_format):
    source = io.BytesIO()
    Image.new("RGB", (32, 24), "red").save(source, format=image_format)
    client = TelegramClient(StringSession(), 12345, "test-hash")

    async def upload(file, **kwargs):
        with Image.open(file) as decoded:
            assert decoded.format in ("JPEG", "PNG")
            assert decoded.size == (32, 24)
        return InputFile(id=1, parts=1, name=file.name, md5_checksum="")

    client.upload_file = AsyncMock(side_effect=upload)

    async def send_file(entity, file, **kwargs):
        assert entity == InputPeerChannel(channel_id=1001, access_hash=42)
        assert kwargs["caption"] == "<b>Post</b>"
        assert kwargs["parse_mode"] == "html"
        _, media, as_image = await client._file_to_media(
            file, force_document=kwargs["force_document"]
        )
        assert as_image is True
        assert isinstance(media, InputMediaUploadedPhoto)
        return SimpleNamespace(id=99)

    client.send_file = AsyncMock(side_effect=send_file)
    provider = TelethonTelegramProvider()
    provider._client = client
    result = await provider.send_message(
        entity_id=1001, access_hash=42, html="<b>Post</b>", image_bytes=source.getvalue()
    )
    assert result.telegram_message_id == 99
    assert result.telegram_channel_id == 1001
    client.upload_file.assert_awaited_once()


async def test_text_only_post_uses_send_message():
    client = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(id=100)))
    provider = TelethonTelegramProvider()
    provider._client = client
    result = await provider.send_message(
        entity_id=1001, access_hash=42, html="<b>Text</b>", image_bytes=None
    )
    client.send_message.assert_awaited_once_with(
        InputPeerChannel(channel_id=1001, access_hash=42), "<b>Text</b>", parse_mode="html"
    )
    assert result.telegram_message_id == 100
