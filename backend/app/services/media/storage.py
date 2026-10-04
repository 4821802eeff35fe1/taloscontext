from __future__ import annotations

import asyncio
import hashlib
import io
import uuid
from functools import lru_cache

import boto3
from botocore.client import Config as BotoConfig

from app.core.config import get_settings

_bucket_ready: set[str] = set()


@lru_cache
def _client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint or None,
        aws_access_key_id=settings.s3_access_key or None,
        aws_secret_access_key=settings.s3_secret_key or None,
        region_name=settings.s3_region,
        config=BotoConfig(
            signature_version="s3v4", connect_timeout=5, read_timeout=30, retries={"max_attempts": 3}
        ),
    )


class MediaStorage:
    """Thin S3-compatible wrapper. Works against MinIO in dev and any
    S3-compatible endpoint in production. Never stores bytes in Postgres.

    boto3 is synchronous; every network call runs in a worker thread so it
    never blocks the event loop.
    """

    def __init__(self):
        self._bucket = get_settings().s3_bucket
        self._client = _client()

    def head_bucket(self) -> None:
        self._client.head_bucket(Bucket=self._bucket)

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:  # noqa: BLE001
            self._client.create_bucket(Bucket=self._bucket)

    async def _ensure_bucket_once(self) -> None:
        if self._bucket not in _bucket_ready:
            await asyncio.to_thread(self.ensure_bucket)
            _bucket_ready.add(self._bucket)

    async def put_object(
        self, data: bytes, *, mime_type: str, workspace_id: uuid.UUID, prefix: str = "media", ext: str | None = None
    ) -> tuple[str, str, str]:
        """Content-addressed upload. Returns (bucket, object_key, checksum_sha256)."""
        await self._ensure_bucket_once()
        checksum = hashlib.sha256(data).hexdigest()
        key = f"{prefix}/{workspace_id}/{checksum}{ext if ext is not None else _ext_for_mime(mime_type)}"
        await asyncio.to_thread(
            self._client.upload_fileobj, io.BytesIO(data), self._bucket, key, ExtraArgs={"ContentType": mime_type}
        )
        return self._bucket, key, checksum

    async def get_object_bytes(self, bucket: str, key: str) -> bytes:
        buf = io.BytesIO()
        await asyncio.to_thread(self._client.download_fileobj, bucket, key, buf)
        return buf.getvalue()

    async def delete_object(self, bucket: str, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=bucket, Key=key)


def _ext_for_mime(mime_type: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "application/pdf": ".pdf",
        "application/json": ".json",
        "text/plain": ".txt",
        "text/markdown": ".md",
        "text/csv": ".csv",
    }.get(mime_type, "")
