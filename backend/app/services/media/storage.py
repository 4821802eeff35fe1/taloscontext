from __future__ import annotations

import hashlib
import io
import uuid

import boto3
from botocore.client import Config as BotoConfig

from app.core.config import get_settings

_bucket_ready: set[str] = set()


class MediaStorage:
    """Thin S3-compatible wrapper. Works against MinIO in dev and any
    S3-compatible endpoint in production. Never stores bytes in Postgres.
    """

    def __init__(self):
        settings = get_settings()
        self._bucket = settings.s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint or None,
            aws_access_key_id=settings.s3_access_key or None,
            aws_secret_access_key=settings.s3_secret_key or None,
            region_name=settings.s3_region,
            config=BotoConfig(signature_version="s3v4"),
        )

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:  # noqa: BLE001
            self._client.create_bucket(Bucket=self._bucket)

    async def put_object(
        self, data: bytes, *, mime_type: str, workspace_id: uuid.UUID, prefix: str = "media"
    ) -> tuple[str, str, str]:
        """Returns (bucket, object_key, checksum_sha256)."""
        if self._bucket not in _bucket_ready:
            self.ensure_bucket()
            _bucket_ready.add(self._bucket)
        checksum = hashlib.sha256(data).hexdigest()
        ext = _ext_for_mime(mime_type)
        key = f"{prefix}/{workspace_id}/{checksum}{ext}"
        self._client.upload_fileobj(
            io.BytesIO(data), self._bucket, key, ExtraArgs={"ContentType": mime_type}
        )
        return self._bucket, key, checksum

    async def get_object_bytes(self, bucket: str, key: str) -> bytes:
        buf = io.BytesIO()
        self._client.download_fileobj(bucket, key, buf)
        return buf.getvalue()

    def generate_presigned_url(self, bucket: str, key: str, expires_in: int = 3600) -> str:
        return self._client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in
        )


def _ext_for_mime(mime_type: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(mime_type, "")
