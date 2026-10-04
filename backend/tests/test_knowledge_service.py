import uuid

import pytest
from sqlalchemy import select

from app.models.knowledge import KnowledgeChunk
from app.services.knowledge.service import KnowledgeService


@pytest.mark.asyncio
async def test_telegram_export_importer_extracts_text_messages(db_session):
    export = {
        "name": "Test Channel",
        "messages": [
            {"type": "message", "date": "2025-01-01T10:00:00", "text": "Hello world"},
            {"type": "service", "date": "2025-01-01T10:01:00", "text": ""},
            {
                "type": "message",
                "date": "2025-01-02T10:00:00",
                "text": [{"type": "bold", "text": "Bold"}, " plain"],
            },
        ],
    }
    service = KnowledgeService(db_session)
    doc = await service.ingest_telegram_export(
        workspace_id=uuid.uuid4(), title="Historical export", export_json=export
    )

    assert "Hello world" in doc.raw_text
    assert "Bold plain" in doc.raw_text
    assert doc.doc_type == "telegram_export"

    chunks = (
        await db_session.execute(select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id))
    ).scalars().all()
    assert len(chunks) >= 1
