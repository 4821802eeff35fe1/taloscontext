"""Content series: numbered parts with a planned topic queue.

A part's number is assigned when its generation is requested, reusing numbers
of parts that were rejected/archived/failed, so the published sequence stays
gap-free. Planned topics are consumed by the parts that use them.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, ContentSeries, SeriesItem
from app.models.enums import ContentStatus

SERIES_STATUSES = ("DRAFT", "ACTIVE", "PAUSED", "COMPLETED")
_DEAD = {ContentStatus.REJECTED, ContentStatus.ARCHIVED, ContentStatus.FAILED}
_DONE = {ContentStatus.PUBLISHED, ContentStatus.PARTIALLY_PUBLISHED}


def label_for(series: ContentSeries, number: int) -> str:
    try:
        return series.numbering_format.format(n=number)
    except (KeyError, ValueError, IndexError):
        return f"#{number:03d}"


def planned_topics(series: ContentSeries) -> list[str]:
    try:
        topics = json.loads(series.planned_topics_json or "[]")
    except json.JSONDecodeError:
        return []
    return [str(t).strip() for t in topics if str(t).strip()]


class SeriesService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _parts(self, series: ContentSeries) -> list[tuple[SeriesItem, ContentItem]]:
        result = await self.session.execute(
            select(SeriesItem, ContentItem)
            .join(ContentItem, SeriesItem.content_item_id == ContentItem.id)
            .where(SeriesItem.series_id == series.id, ContentItem.deleted_at.is_(None))
            .order_by(SeriesItem.sequence_number)
        )
        return [(si, ci) for si, ci in result.all()]

    async def progress(self, series: ContentSeries) -> dict[str, Any]:
        parts = await self._parts(series)
        alive = [(si, ci) for si, ci in parts if ci.status not in _DEAD]
        used_topics = {ci.topic.strip().lower() for _, ci in alive if ci.topic}
        remaining = [t for t in planned_topics(series) if t.lower() not in used_topics]
        next_number = self._next_number(alive)
        return {
            "items": [
                {"label": label_for(series, si.sequence_number), "number": si.sequence_number,
                 "title": ci.title or ci.topic, "status": ci.status.value, "content_id": str(ci.id)}
                for si, ci in alive if ci.status in _DONE
            ],
            "in_progress": [
                {"label": label_for(series, si.sequence_number), "number": si.sequence_number,
                 "title": ci.title or ci.topic, "status": ci.status.value, "content_id": str(ci.id)}
                for si, ci in alive if ci.status not in _DONE
            ],
            "published_count": sum(1 for _, ci in alive if ci.status in _DONE),
            "planned_count": len(planned_topics(series)),
            "remaining_topics": remaining,
            "next_topic": remaining[0] if remaining else None,
            "next_number": next_number,
            "next_label": label_for(series, next_number),
        }

    @staticmethod
    def _next_number(alive: list[tuple[SeriesItem, ContentItem]]) -> int:
        taken = {si.sequence_number for si, _ in alive}
        n = 1
        while n in taken:
            n += 1
        return n

    async def attach(self, series: ContentSeries, item: ContentItem) -> SeriesItem:
        parts = await self._parts(series)
        alive = [(si, ci) for si, ci in parts if ci.status not in _DEAD]
        number = self._next_number(alive)
        row = SeriesItem(series_id=series.id, content_item_id=item.id, sequence_number=number)
        self.session.add(row)
        series.sequence_counter = max(series.sequence_counter or 0, number)
        item.series_id = series.id
        await self.session.flush()
        return row

    async def get_for_workspace(self, workspace_id: uuid.UUID, series_id: uuid.UUID) -> ContentSeries | None:
        series = await self.session.get(ContentSeries, series_id)
        return series if series and series.workspace_id == workspace_id else None
