from __future__ import annotations

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeChunk, KnowledgeDocument

CHUNK_SIZE_CHARS = 1200


class KnowledgeService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def ingest_text(
        self, *, workspace_id: uuid.UUID, title: str, doc_type: str, raw_text: str, tags: list[str] | None = None
    ) -> KnowledgeDocument:
        doc = KnowledgeDocument(
            workspace_id=workspace_id,
            title=title,
            doc_type=doc_type,
            raw_text=raw_text,
            tags_json=json.dumps(tags or [], ensure_ascii=False),
        )
        self.session.add(doc)
        await self.session.flush()
        await self._chunk(doc)
        return doc

    async def ingest_telegram_export(
        self, *, workspace_id: uuid.UUID, title: str, export_json: dict
    ) -> KnowledgeDocument:
        """Parses a standard Telegram Desktop JSON export (`result.json`):
        { "name": ..., "messages": [ { "date": ..., "text": ..., "text_entities": [...] } ] }
        """
        messages = export_json.get("messages", [])
        lines: list[str] = []
        for msg in messages:
            if msg.get("type") != "message":
                continue
            text = msg.get("text")
            if isinstance(text, list):
                text = "".join(part if isinstance(part, str) else part.get("text", "") for part in text)
            if not text:
                continue
            date = msg.get("date", "")
            lines.append(f"[{date}] {text}")

        raw_text = "\n\n".join(lines)
        return await self.ingest_text(
            workspace_id=workspace_id,
            title=title,
            doc_type="telegram_export",
            raw_text=raw_text,
            tags=["telegram-export", "historical"],
        )

    async def _chunk(self, doc: KnowledgeDocument) -> None:
        text = doc.raw_text
        for i, start in enumerate(range(0, len(text), CHUNK_SIZE_CHARS)):
            chunk_text = text[start : start + CHUNK_SIZE_CHARS]
            self.session.add(
                KnowledgeChunk(document_id=doc.id, chunk_index=i, content=chunk_text)
            )
        await self.session.flush()

    async def build_context(self, *, workspace_id: uuid.UUID, max_chars: int = 3000) -> str:
        from sqlalchemy import select

        result = await self.session.execute(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.workspace_id == workspace_id)
            .where(KnowledgeDocument.doc_type.in_(["facts", "allowed_claims", "prohibited_claims", "company_info"]))
            .order_by(KnowledgeDocument.updated_at.desc())
            .limit(10)
        )
        docs = result.scalars().all()
        parts = [f"[{d.doc_type}] {d.title}: {d.raw_text[:500]}" for d in docs]
        context = "\n".join(parts)
        return context[:max_chars]
