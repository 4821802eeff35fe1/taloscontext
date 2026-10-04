"""Knowledge ingestion: parse uploads into typed, chunked entries.

Each chunk carries a kind (see context.KNOWLEDGE_KINDS) and an effective
date, which is what lets the prompt builder rank current facts above old
posts. Parsers are deliberately simple and deterministic — no AI calls.
"""
from __future__ import annotations

import csv
import io
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.services.content.context import KNOWLEDGE_KINDS

CHUNK_SIZE_CHARS = 1200
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000
MAX_CHUNKS = 5000
FORMATS = ("txt", "md", "json", "csv", "pdf")


class KnowledgeParseError(ValueError):
    pass


def _split_text(text: str, size: int = CHUNK_SIZE_CHARS) -> list[str]:
    """Paragraph-aware chunking: keeps paragraphs/bullets together up to `size`."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n(?=\s*[-*•]\s)|\n(?=#+\s)", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for p in paragraphs:
        while len(p) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(p[:size])
            p = p[size:]
        if current and len(current) + len(p) + 2 > size:
            chunks.append(current)
            current = p
        else:
            current = f"{current}\n\n{p}" if current else p
    if current:
        chunks.append(current)
    return chunks


def _message_text(msg: dict) -> str:
    text = msg.get("text", "")
    if isinstance(text, list):
        text = "".join(part if isinstance(part, str) else part.get("text", "") for part in text)
    return str(text or "").strip()


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def is_telegram_export(data: Any) -> bool:
    return isinstance(data, dict) and isinstance(data.get("messages"), list) and (
        "name" in data or "type" in data or any(isinstance(m, dict) and "date" in m for m in data["messages"][:5])
    )


def parse_telegram_export(data: dict) -> tuple[list[dict], list[str]]:
    """Standard Telegram Desktop export (result.json) -> one entry per post."""
    channel = {"name": data.get("name"), "id": data.get("id"), "type": data.get("type")}
    entries, warnings = [], []
    skipped_service = skipped_empty = 0
    for msg in data["messages"]:
        if not isinstance(msg, dict):
            continue
        if msg.get("type") != "message":
            skipped_service += 1
            continue
        text = _message_text(msg)
        if not text:
            skipped_empty += 1
            continue
        media = {k: msg[k] for k in ("media_type", "mime_type", "width", "height", "duration_seconds", "file_name")
                 if k in msg}
        if "photo" in msg:
            media["photo"] = True
        entries.append({
            "content": text,
            "effective_at": _parse_date(msg.get("date")),
            "metadata": {
                "message_id": msg.get("id"),
                "date": msg.get("date"),
                "entities": msg.get("text_entities", []),
                "media": media or None,
                "source_channel": channel,
                "views": msg.get("views"),
            },
        })
    if skipped_service:
        warnings.append(f"Skipped {skipped_service} service messages")
    if skipped_empty:
        warnings.append(f"Skipped {skipped_empty} posts without text (media only)")
    return entries, warnings


def parse_upload(filename: str, data: bytes) -> tuple[str, list[dict], list[str], bool]:
    """Returns (format, entries, warnings, is_telegram_export)."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise KnowledgeParseError(f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in FORMATS:
        raise KnowledgeParseError(f"Unsupported file type .{ext}; use {', '.join('.' + f for f in FORMATS)}")
    warnings: list[str] = []

    if ext == "pdf":
        if not data.startswith(b"%PDF"):
            raise KnowledgeParseError("File is not a valid PDF")
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [(page.extract_text() or "") for page in reader.pages]
        except (PdfReadError, ValueError) as exc:
            raise KnowledgeParseError(f"Could not read PDF: {exc}") from exc
        text = "\n\n".join(p for p in pages if p.strip())
        if not text.strip():
            raise KnowledgeParseError("No extractable text in this PDF (scanned image?)")
        return ext, [{"content": c} for c in _split_text(text[:MAX_TEXT_CHARS])], warnings, False

    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise KnowledgeParseError("File must be UTF-8 text") from exc
    if len(text) > MAX_TEXT_CHARS:
        warnings.append(f"Text truncated to {MAX_TEXT_CHARS} characters")
        text = text[:MAX_TEXT_CHARS]

    if ext == "json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise KnowledgeParseError(f"Invalid JSON: {exc.msg} at line {exc.lineno}") from exc
        if is_telegram_export(parsed):
            entries, tg_warnings = parse_telegram_export(parsed)
            return ext, entries, warnings + tg_warnings, True
        items = parsed if isinstance(parsed, list) else [parsed]
        entries = []
        for item in items:
            if isinstance(item, str):
                entries.append({"content": item})
            elif isinstance(item, dict):
                body = item.get("text") or item.get("content") or json.dumps(item, ensure_ascii=False)
                entries.append({"content": str(body), "kind": item.get("kind"),
                                "effective_at": _parse_date(item.get("updated_at") or item.get("date"))})
        return ext, entries, warnings, False

    if ext == "csv":
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise KnowledgeParseError("CSV has no header row")
        entries = []
        for row in reader:
            kind = (row.pop("kind", None) or row.pop("type", None) or "").strip().upper() or None
            updated = _parse_date(row.pop("updated_at", None) or row.pop("date", None))
            body = row.pop("text", None) or row.pop("content", None)
            if not body:
                body = "; ".join(f"{k}: {v}" for k, v in row.items() if k and v)
            if body and body.strip():
                entries.append({"content": body.strip(), "kind": kind, "effective_at": updated})
        return ext, entries, warnings, False

    return ext, [{"content": c} for c in _split_text(text)], warnings, False


class KnowledgeService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_document(
        self,
        *,
        workspace_id: uuid.UUID,
        title: str,
        kind: str,
        doc_format: str,
        entries: list[dict],
        knowledge_base_id: uuid.UUID | None = None,
        source_filename: str = "",
        valid_until: datetime | None = None,
        warnings: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> KnowledgeDocument:
        if kind not in KNOWLEDGE_KINDS:
            raise KnowledgeParseError(f"Unknown kind {kind}")
        if not entries:
            raise KnowledgeParseError("Nothing to import: the file has no usable text")
        warnings = list(warnings or [])
        if len(entries) > MAX_CHUNKS:
            warnings.append(f"Only the first {MAX_CHUNKS} entries were imported")
            entries = entries[:MAX_CHUNKS]
        doc = KnowledgeDocument(
            workspace_id=workspace_id, knowledge_base_id=knowledge_base_id, title=title[:300], doc_type=doc_format,
            kind=kind, source_filename=source_filename[:300], valid_until=valid_until,
            raw_text="\n\n".join(e["content"] for e in entries)[:MAX_TEXT_CHARS],
            tags_json=json.dumps(tags or [], ensure_ascii=False),
            parse_warnings_json=json.dumps(warnings, ensure_ascii=False),
        )
        self.session.add(doc)
        await self.session.flush()
        now = datetime.now(UTC)
        for i, entry in enumerate(entries):
            entry_kind = (entry.get("kind") or kind).upper()
            self.session.add(KnowledgeChunk(
                document_id=doc.id, chunk_index=i, content=entry["content"][:CHUNK_SIZE_CHARS * 4],
                kind=entry_kind if entry_kind in KNOWLEDGE_KINDS else kind,
                effective_at=entry.get("effective_at") or now,
                metadata_json=json.dumps(entry.get("metadata") or {}, ensure_ascii=False, default=str),
            ))
        await self.session.flush()
        return doc

    async def ingest_text(
        self, *, workspace_id: uuid.UUID, title: str, doc_type: str, raw_text: str, tags: list[str] | None = None,
        kind: str = "FACT",
    ) -> KnowledgeDocument:
        return await self.create_document(
            workspace_id=workspace_id, title=title, kind=kind, doc_format=doc_type,
            entries=[{"content": c} for c in _split_text(raw_text)], tags=tags,
        )

    async def ingest_telegram_export(
        self, *, workspace_id: uuid.UUID, title: str, export_json: dict, kind: str = "HISTORICAL_POST"
    ) -> KnowledgeDocument:
        entries, warnings = parse_telegram_export(export_json)
        return await self.create_document(
            workspace_id=workspace_id, title=title, kind=kind, doc_format="telegram_export",
            entries=entries, warnings=warnings, tags=["telegram-export"],
        )

    async def search(self, workspace_id: uuid.UUID, query: str, limit: int = 30) -> list[tuple[KnowledgeChunk, KnowledgeDocument]]:
        pattern = f"%{query.lower()}%"
        rows = await self.session.execute(
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(
                KnowledgeDocument.workspace_id == workspace_id,
                or_(func.lower(KnowledgeChunk.content).like(pattern), func.lower(KnowledgeDocument.title).like(pattern)),
            )
            .order_by(KnowledgeChunk.effective_at.desc())
            .limit(limit)
        )
        return [(c, d) for c, d in rows.all()]
