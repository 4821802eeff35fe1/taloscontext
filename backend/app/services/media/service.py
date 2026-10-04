from __future__ import annotations

import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MediaStatus
from app.models.media import MediaAsset
from app.services.media.storage import MediaStorage

ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024

_MAGIC_BYTES: dict[bytes, str] = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
}


class UnsupportedMediaError(Exception):
    pass


def sniff_mime_type(data: bytes) -> str | None:
    for magic, mime in _MAGIC_BYTES.items():
        if data.startswith(magic):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def sanitize_filename(filename: str) -> str:
    filename = filename.strip().replace("/", "_").replace("\\", "_")
    filename = re.sub(r"[^\w.\-]", "_", filename)
    return filename[:200] or "upload"


class MediaService:
    def __init__(self, session: AsyncSession, storage: MediaStorage):
        self.session = session
        self.storage = storage

    async def upload(
        self, *, workspace_id: uuid.UUID, data: bytes, original_filename: str
    ) -> MediaAsset:
        if len(data) > MAX_UPLOAD_BYTES:
            raise UnsupportedMediaError(f"File exceeds {MAX_UPLOAD_BYTES} bytes limit")

        mime_type = sniff_mime_type(data)
        if mime_type is None or mime_type not in ALLOWED_MIME_TYPES:
            raise UnsupportedMediaError("Unsupported or unrecognized image format")

        bucket, key, checksum = await self.storage.put_object(
            data, mime_type=mime_type, workspace_id=workspace_id, prefix="uploads"
        )
        width, height = _try_read_dimensions(data, mime_type)

        asset = MediaAsset(
            workspace_id=workspace_id,
            bucket=bucket,
            object_key=key,
            mime_type=mime_type,
            width=width,
            height=height,
            size_bytes=len(data),
            checksum_sha256=checksum,
            original_filename=sanitize_filename(original_filename),
            status=MediaStatus.UPLOADED,
        )
        self.session.add(asset)
        await self.session.flush()
        return asset

    async def store_generated(
        self, *, workspace_id: uuid.UUID, data: bytes, mime_type: str
    ) -> MediaAsset:
        bucket, key, checksum = await self.storage.put_object(
            data, mime_type=mime_type, workspace_id=workspace_id, prefix="generated"
        )
        width, height = _try_read_dimensions(data, mime_type)
        asset = MediaAsset(
            workspace_id=workspace_id,
            bucket=bucket,
            object_key=key,
            mime_type=mime_type,
            width=width,
            height=height,
            size_bytes=len(data),
            checksum_sha256=checksum,
            status=MediaStatus.GENERATED,
        )
        self.session.add(asset)
        await self.session.flush()
        return asset


def _try_read_dimensions(data: bytes, mime_type: str) -> tuple[int | None, int | None]:
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            return img.width, img.height
    except Exception:  # noqa: BLE001
        return None, None
