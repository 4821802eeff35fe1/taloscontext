"""Source fetching for the Ideas inbox. Fetching never generates posts.

Kinds:
  rss       — feed URL; one idea per entry
  url       — a website page; one idea per new <article>/headline link (best effort)
  manual    — a single URL saved by hand; fetched once for title/summary
  telegram  — a public channel readable by a connected account (via TelegramProvider)

Outbound HTTP goes through `safe_get`: SSRF check on the URL and on every
redirect hop, size cap, timeouts.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from urllib.parse import urljoin

import feedparser
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import IdeaStatus
from app.models.sources import Source, SourceItem
from app.services.security.ssrf_guard import SSRFBlockedError, assert_url_is_safe

MAX_BYTES = 3 * 1024 * 1024
MAX_REDIRECTS = 5
MAX_ITEMS_PER_FETCH = 30
USER_AGENT = "ChannelOS/0.2 (+source fetcher)"
SOURCE_KINDS = ("rss", "url", "manual", "telegram")


class SourceFetchError(Exception):
    pass


async def safe_get(url: str, *, timeout: float = 15.0) -> httpx.Response:
    current = url
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers={"User-Agent": USER_AGENT}) as client:
        for _ in range(MAX_REDIRECTS + 1):
            try:
                assert_url_is_safe(current)
            except SSRFBlockedError as exc:
                raise SourceFetchError(f"Blocked URL: {exc}") from exc
            async with client.stream("GET", current) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise SourceFetchError("Redirect without location")
                    current = urljoin(current, location)
                    continue
                if response.status_code >= 400:
                    raise SourceFetchError(f"HTTP {response.status_code} from {current}")
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise SourceFetchError("Response too large")
                    chunks.append(chunk)
                return httpx.Response(response.status_code, headers=response.headers, content=b"".join(chunks),
                                      request=response.request)
    raise SourceFetchError("Too many redirects")


async def verify_url(url: str) -> bool:
    """Syntactically valid, public, and answering with < 400."""
    try:
        await safe_get(url, timeout=6.0)
        return True
    except (SourceFetchError, httpx.HTTPError):
        return False


def _clean(text: str, limit: int) -> str:
    return " ".join(BeautifulSoup(text or "", "html.parser").get_text(" ").split())[:limit]


def _parse_date(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime(*parsed[:6], tzinfo=UTC)


def _freshness(published_at: datetime | None, now: datetime) -> float:
    if published_at is None:
        return 0.3
    hours = max(0.0, (now - published_at).total_seconds() / 3600)
    return round(max(0.0, 1 - hours / (24 * 7)), 3)  # linear decay over a week


class SourceService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def config(source: Source) -> dict:
        try:
            return json.loads(source.config_json or "{}")
        except json.JSONDecodeError:
            return {}

    async def _known_urls(self, source: Source) -> set[str]:
        rows = await self.session.execute(select(SourceItem.url).where(SourceItem.source_id == source.id))
        return {r[0] for r in rows.all() if r[0]}

    def _relevance(self, source: Source, text: str) -> float:
        keywords = [k.lower() for k in self.config(source).get("keywords", []) if k]
        if not keywords:
            return 0.5
        low = text.lower()
        return round(sum(1 for k in keywords if k in low) / len(keywords), 3)

    async def fetch(self, source: Source) -> int:
        """Fetches new items; returns how many were added. Records success/error on the source."""
        now = datetime.now(UTC)
        config = self.config(source)
        source.last_fetched_at = now
        try:
            if source.kind == "rss":
                candidates = await self._fetch_rss(config.get("url", ""))
            elif source.kind in ("url", "manual"):
                candidates = await self._fetch_page(config.get("url", ""), single=source.kind == "manual")
            elif source.kind == "telegram":
                candidates = await self._fetch_telegram(source, config)
            else:
                raise SourceFetchError(f"Unsupported source kind {source.kind}")
        except (SourceFetchError, httpx.HTTPError) as exc:
            config["last_error"] = str(exc)[:500]
            source.config_json = json.dumps(config)
            await self.session.flush()
            raise SourceFetchError(str(exc)) from exc

        known = await self._known_urls(source)
        added = 0
        for title, summary, url, published_at in candidates[:MAX_ITEMS_PER_FETCH]:
            key = url or hashlib.sha256(f"{title}|{summary}".encode()).hexdigest()
            if key in known or not title:
                continue
            known.add(key)
            self.session.add(SourceItem(
                source_id=source.id, workspace_id=source.workspace_id, title=title[:500], summary=summary[:2000],
                url=key if url else "", url_verified=bool(url),  # fetched over HTTP successfully
                published_at=published_at, freshness_score=_freshness(published_at, now),
                relevance_score=self._relevance(source, f"{title} {summary}"),
                category=config.get("category", "news"), status=IdeaStatus.NEW,
            ))
            added += 1
        config.pop("last_error", None)
        config["last_success_at"] = now.isoformat()
        source.config_json = json.dumps(config)
        await self.session.flush()
        return added

    async def _fetch_rss(self, url: str) -> list[tuple[str, str, str, datetime | None]]:
        response = await safe_get(url)
        parsed = feedparser.parse(response.content)
        if parsed.bozo and not parsed.entries:
            raise SourceFetchError("Not a valid RSS/Atom feed")
        return [
            (_clean(e.get("title", ""), 500), _clean(e.get("summary", ""), 2000), e.get("link", ""), _parse_date(e))
            for e in parsed.entries
        ]

    async def _fetch_page(self, url: str, *, single: bool) -> list[tuple[str, str, str, datetime | None]]:
        response = await safe_get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        if single:
            title = (soup.find("meta", property="og:title") or {}).get("content") or (soup.title.string if soup.title else url)
            desc = (soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"}) or {}).get("content", "")
            return [(_clean(title or url, 500), _clean(desc, 2000), url, None)]
        out = []
        for node in soup.select("article a[href], h2 a[href], h3 a[href]")[:MAX_ITEMS_PER_FETCH * 2]:
            text = _clean(node.get_text(), 300)
            href = urljoin(url, node["href"])
            if len(text) >= 15 and href.startswith(("http://", "https://")):
                out.append((text, "", href, None))
        return out

    async def _fetch_telegram(self, source: Source, config: dict) -> list[tuple[str, str, str, datetime | None]]:
        from app.core.security import decrypt_session_string
        from app.models.telegram import TelegramAccount
        from app.services.telegram.factory import new_provider

        username = (config.get("channel") or "").lstrip("@")
        if not username:
            raise SourceFetchError("Telegram source needs a channel username")
        account = await self.session.get(TelegramAccount, uuid.UUID(config["account_id"])) if config.get("account_id") else None
        if account is None or account.workspace_id != source.workspace_id or not account.session_encrypted:
            raise SourceFetchError("Choose a connected Telegram account that can read this channel")
        provider = new_provider()
        try:
            await provider.restore_session(decrypt_session_string(account.session_encrypted))
            posts = await provider.read_channel_posts(username=username, limit=MAX_ITEMS_PER_FETCH)
        finally:
            await provider.disconnect()
        return [
            (p.text.split("\n", 1)[0][:300], p.text[:2000], f"https://t.me/{username}/{p.message_id}", p.date)
            for p in posts if p.text
        ]
