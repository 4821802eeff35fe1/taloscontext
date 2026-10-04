import uuid

from app.models.media import MediaAsset
from tests.conftest import register


async def test_download_filename_supports_unicode_without_header_injection(client, session_factory, monkeypatch):
    ws = await register(client, "download@example.com")
    async with session_factory() as db:
        asset = MediaAsset(workspace_id=uuid.UUID(ws), bucket="test", object_key="safe/key",
                           checksum_sha256="a" * 64, size_bytes=4, mime_type="image/png",
                           original_filename='Картинка"\r\nInjected: header.png')
        db.add(asset)
        await db.commit()
        asset_id = asset.id

    async def read(*args):
        return b"test"

    monkeypatch.setattr("app.services.media.storage.MediaStorage.get_object_bytes", read)
    response = await client.get(f"/api/v1/workspaces/{ws}/media/{asset_id}/content?download=true")
    assert response.status_code == 200
    assert response.content == b"test"
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    assert "%0D%0A" in response.headers["content-disposition"]
    assert "Injected" not in response.headers
