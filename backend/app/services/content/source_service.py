from __future__ import annotations

from datetime import UTC, datetime

import feedparser
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import IdeaStatus
from app.models.sources import Source, SourceItem
from app.services.security.ssrf_guard import SSRFBlockedError, assert_url_is_safe


class SourceService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def fetch_rss(self, source: Source) -> list[SourceItem]:
        import json

        config = json.loads(source.config_json or "{}")
        feed_url = config.get("url", "")
        try:
            assert_url_is_safe(feed_url)
        except SSRFBlockedError:
            return []

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            response = await client.get(feed_url)
            response.raise_for_status()

        parsed = feedparser.parse(response.text)
        items: list[SourceItem] = []
        for entry in parsed.entries[:20]:
            url = entry.get("link", "")
            url_ok = _verify_url_sync(url)
            item = SourceItem(
                source_id=source.id,
                workspace_id=source.workspace_id,
                title=entry.get("title", "")[:500],
                summary=entry.get("summary", "")[:2000],
                url=url,
                url_verified=url_ok,
                category="news",
                status=IdeaStatus.NEW,
            )
            self.session.add(item)
            items.append(item)

        source.last_fetched_at = datetime.now(UTC)
        await self.session.flush()
        return items


def _verify_url_sync(url: str) -> bool:
    if not url:
        return False
    try:
        assert_url_is_safe(url)
    except SSRFBlockedError:
        return False
    try:
        with httpx.Client(timeout=5.0, follow_redirects=True) as client:
            response = client.head(url)
            return response.status_code < 400
    except Exception:  # noqa: BLE001
        return False
