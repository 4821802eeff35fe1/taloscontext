"""Outbound requests must use the validated address, including redirects."""
import httpx
import pytest

from app.services.content import source_service


async def test_dns_is_pinned_and_redirect_revalidated(monkeypatch):
    requested = []
    resolved = []

    def resolve(url):
        resolved.append(url)
        return ["93.184.216.34"]

    async def handle(request):
        requested.append(request)
        if request.url.path == "/first":
            return httpx.Response(302, headers={"location": "https://other.example/article"})
        return httpx.Response(200, text="Article")

    original_client = httpx.AsyncClient
    monkeypatch.setattr(source_service, "resolve_public_addresses", resolve)
    monkeypatch.setattr(source_service.httpx, "AsyncClient", lambda **kwargs: original_client(
        **kwargs, transport=httpx.MockTransport(handle)))
    response = await source_service.safe_get("https://source.example/first")
    assert response.text == "Article"
    assert resolved == ["https://source.example/first", "https://other.example/article"]
    assert all(r.url.host == "93.184.216.34" for r in requested)
    assert [r.headers["host"] for r in requested] == ["source.example", "other.example"]
    assert [r.extensions["sni_hostname"] for r in requested] == ["source.example", "other.example"]


async def test_redirect_to_private_network_never_sent(monkeypatch):
    requested = []

    def resolve(url):
        if "127.0.0.1" in url:
            raise source_service.SSRFBlockedError("private network")
        return ["93.184.216.34"]

    async def handle(request):
        requested.append(request)
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(source_service, "resolve_public_addresses", resolve)
    monkeypatch.setattr(source_service.httpx, "AsyncClient", lambda **kwargs: original_client(
        **kwargs, transport=httpx.MockTransport(handle)))
    with pytest.raises(source_service.SourceFetchError, match="Blocked URL"):
        await source_service.safe_get("https://source.example/first")
    assert len(requested) == 1
