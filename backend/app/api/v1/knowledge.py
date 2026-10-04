from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_workspace_member
from app.core.errors import ApiError
from app.core.rbac import CAN_EDIT_CONTENT, require_role
from app.models.identity import User, WorkspaceMember
from app.models.knowledge import KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from app.services.audit.service import AuditService
from app.services.content.context import KNOWLEDGE_KINDS
from app.services.knowledge.service import (
    MAX_UPLOAD_BYTES,
    KnowledgeParseError,
    KnowledgeService,
    _split_text,
    parse_upload,
)
from app.services.media.service import sanitize_filename

router = APIRouter(prefix="/workspaces/{workspace_id}/knowledge", tags=["knowledge"])


class BaseIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    enabled: bool = True


class BaseOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    enabled: bool
    documents: int
    entries: int
    created_at: datetime


class DocumentOut(BaseModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID | None
    title: str
    kind: str
    format: str
    enabled: bool
    valid_until: datetime | None
    source_filename: str
    entries: int
    warnings: list[str]
    updated_at: datetime


class EntryOut(BaseModel):
    id: uuid.UUID
    index: int
    kind: str
    content: str
    effective_at: datetime | None
    metadata: dict


class DocumentDetail(DocumentOut):
    preview: list[EntryOut]


class ManualEntryIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    kind: str = "FACT"
    text: str = Field(min_length=1, max_length=50_000)
    knowledge_base_id: uuid.UUID | None = None
    valid_until: datetime | None = None


class DocumentPatch(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    kind: str | None = None
    enabled: bool | None = None
    valid_until: datetime | None = None
    clear_valid_until: bool = False


class SearchHit(BaseModel):
    document_id: uuid.UUID
    document_title: str
    kind: str
    snippet: str
    effective_at: datetime | None


def _check_kind(kind: str) -> str:
    kind = kind.upper()
    if kind not in KNOWLEDGE_KINDS:
        raise ApiError(422, "KNOWLEDGE_KIND_INVALID", f"kind must be one of {', '.join(KNOWLEDGE_KINDS)}", kind=kind)
    return kind


async def _base_or_404(db, workspace_id, base_id) -> KnowledgeBase:
    kb = await db.get(KnowledgeBase, base_id)
    if kb is None or kb.workspace_id != workspace_id:
        raise ApiError(404, "KNOWLEDGE_BASE_NOT_FOUND", "Knowledge base not found")
    return kb


async def _doc_or_404(db, workspace_id, doc_id) -> KnowledgeDocument:
    doc = await db.get(KnowledgeDocument, doc_id)
    if doc is None or doc.workspace_id != workspace_id:
        raise ApiError(404, "KNOWLEDGE_DOCUMENT_NOT_FOUND", "Document not found")
    return doc


async def _base_out(db, kb: KnowledgeBase) -> BaseOut:
    documents = await db.scalar(select(func.count()).select_from(KnowledgeDocument)
                                .where(KnowledgeDocument.knowledge_base_id == kb.id))
    entries = await db.scalar(select(func.count()).select_from(KnowledgeChunk)
                              .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
                              .where(KnowledgeDocument.knowledge_base_id == kb.id))
    return BaseOut(id=kb.id, name=kb.name, description=kb.description, enabled=kb.enabled,
                   documents=documents or 0, entries=entries or 0, created_at=kb.created_at)


async def _doc_out(db, doc: KnowledgeDocument, count: int | None = None) -> DocumentOut:
    if count is None:
        count = await db.scalar(select(func.count()).select_from(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id))
    return DocumentOut(
        id=doc.id, knowledge_base_id=doc.knowledge_base_id, title=doc.title, kind=doc.kind, format=doc.doc_type,
        enabled=doc.enabled, valid_until=doc.valid_until, source_filename=doc.source_filename, entries=count or 0,
        warnings=json.loads(doc.parse_warnings_json or "[]"), updated_at=doc.updated_at,
    )


@router.get("/bases", response_model=list[BaseOut])
async def list_bases(workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member),
                     db: AsyncSession = Depends(get_db)):
    bases = (await db.execute(select(KnowledgeBase).where(KnowledgeBase.workspace_id == workspace_id)
                              .order_by(KnowledgeBase.created_at))).scalars().all()
    docs = dict((await db.execute(select(KnowledgeDocument.knowledge_base_id, func.count())
                                  .where(KnowledgeDocument.workspace_id == workspace_id)
                                  .group_by(KnowledgeDocument.knowledge_base_id))).all())
    entries = dict((await db.execute(
        select(KnowledgeDocument.knowledge_base_id, func.count()).join(KnowledgeChunk, KnowledgeChunk.document_id == KnowledgeDocument.id)
        .where(KnowledgeDocument.workspace_id == workspace_id).group_by(KnowledgeDocument.knowledge_base_id))).all())
    return [BaseOut(id=b.id, name=b.name, description=b.description, enabled=b.enabled, documents=docs.get(b.id, 0),
                    entries=entries.get(b.id, 0), created_at=b.created_at) for b in bases]


@router.post("/bases", response_model=BaseOut, status_code=status.HTTP_201_CREATED)
async def create_base(workspace_id: uuid.UUID, payload: BaseIn, member: WorkspaceMember = Depends(get_workspace_member),
                      user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_role(member.role, CAN_EDIT_CONTENT)
    kb = KnowledgeBase(workspace_id=workspace_id, name=payload.name, description=payload.description, enabled=payload.enabled)
    db.add(kb)
    await db.flush()
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="knowledge.base_created",
                                  entity_type="knowledge_base", entity_id=kb.id, metadata={"name": kb.name})
    await db.commit()
    return BaseOut(id=kb.id, name=kb.name, description=kb.description, enabled=kb.enabled, documents=0, entries=0,
                   created_at=kb.created_at)


@router.patch("/bases/{base_id}", response_model=BaseOut)
async def update_base(workspace_id: uuid.UUID, base_id: uuid.UUID, payload: BaseIn,
                      member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    require_role(member.role, CAN_EDIT_CONTENT)
    kb = await _base_or_404(db, workspace_id, base_id)
    kb.name, kb.description, kb.enabled = payload.name, payload.description, payload.enabled
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="knowledge.base_updated",
                                  entity_type="knowledge_base", entity_id=kb.id, metadata={"enabled": kb.enabled})
    await db.commit()
    return await _base_out(db, kb)


@router.delete("/bases/{base_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_base(workspace_id: uuid.UUID, base_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member),
                      user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_role(member.role, CAN_EDIT_CONTENT)
    kb = await _base_or_404(db, workspace_id, base_id)
    await db.delete(kb)
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="knowledge.base_deleted",
                                  entity_type="knowledge_base", entity_id=base_id, metadata={"name": kb.name})
    await db.commit()


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(workspace_id: uuid.UUID, base_id: uuid.UUID | None = None, kind: str | None = None,
                         member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db)):
    stmt = select(KnowledgeDocument).where(KnowledgeDocument.workspace_id == workspace_id)
    if base_id:
        stmt = stmt.where(KnowledgeDocument.knowledge_base_id == base_id)
    if kind:
        stmt = stmt.where(KnowledgeDocument.kind == kind.upper())
    docs = (await db.execute(stmt.order_by(KnowledgeDocument.updated_at.desc()))).scalars().all()
    counts = dict((await db.execute(select(KnowledgeChunk.document_id, func.count())
                                    .where(KnowledgeChunk.document_id.in_([d.id for d in docs]))
                                    .group_by(KnowledgeChunk.document_id))).all()) if docs else {}
    return [await _doc_out(db, d, counts.get(d.id, 0)) for d in docs]


@router.post("/documents/upload", response_model=DocumentDetail, status_code=status.HTTP_201_CREATED)
async def upload_document(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    kind: str = Form("FACT"),
    knowledge_base_id: uuid.UUID | None = Form(None),
    title: str = Form(""),
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    kind = _check_kind(kind)
    if knowledge_base_id:
        await _base_or_404(db, workspace_id, knowledge_base_id)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    filename = sanitize_filename(file.filename or "upload.txt")
    try:
        fmt, entries, warnings, is_tg = parse_upload(filename, data)
        if is_tg and kind == "FACT":
            kind = "HISTORICAL_POST"  # an export of old posts is never authoritative by default
        doc = await KnowledgeService(db).create_document(
            workspace_id=workspace_id, title=title or filename, kind=kind,
            doc_format="telegram_export" if is_tg else fmt, entries=entries, knowledge_base_id=knowledge_base_id,
            source_filename=filename, warnings=warnings,
        )
    except KnowledgeParseError as exc:
        raise ApiError(422, "KNOWLEDGE_PARSE_ERROR", str(exc)) from exc
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="knowledge.uploaded",
                                  entity_type="knowledge_document", entity_id=doc.id,
                                  metadata={"file": filename, "kind": kind, "entries": len(entries)})
    await db.commit()
    return await get_document(workspace_id, doc.id, member, db)


@router.post("/documents", response_model=DocumentDetail, status_code=status.HTTP_201_CREATED)
async def create_manual(workspace_id: uuid.UUID, payload: ManualEntryIn,
                        member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    require_role(member.role, CAN_EDIT_CONTENT)
    kind = _check_kind(payload.kind)
    if payload.knowledge_base_id:
        await _base_or_404(db, workspace_id, payload.knowledge_base_id)
    doc = await KnowledgeService(db).create_document(
        workspace_id=workspace_id, title=payload.title, kind=kind, doc_format="manual",
        entries=[{"content": c} for c in _split_text(payload.text)], knowledge_base_id=payload.knowledge_base_id,
        valid_until=payload.valid_until,
    )
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="knowledge.created",
                                  entity_type="knowledge_document", entity_id=doc.id, metadata={"kind": kind})
    await db.commit()
    return await get_document(workspace_id, doc.id, member, db)


@router.get("/documents/{doc_id}", response_model=DocumentDetail)
async def get_document(workspace_id: uuid.UUID, doc_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member),
                       db: AsyncSession = Depends(get_db)):
    doc = await _doc_or_404(db, workspace_id, doc_id)
    chunks = (await db.execute(select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id)
                               .order_by(KnowledgeChunk.chunk_index).limit(50))).scalars().all()
    out = await _doc_out(db, doc)
    return DocumentDetail(**out.model_dump(), preview=[
        EntryOut(id=c.id, index=c.chunk_index, kind=c.kind, content=c.content, effective_at=c.effective_at,
                 metadata=json.loads(c.metadata_json or "{}")) for c in chunks])


@router.patch("/documents/{doc_id}", response_model=DocumentOut)
async def update_document(workspace_id: uuid.UUID, doc_id: uuid.UUID, payload: DocumentPatch,
                          member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    require_role(member.role, CAN_EDIT_CONTENT)
    doc = await _doc_or_404(db, workspace_id, doc_id)
    if payload.title is not None:
        doc.title = payload.title
    if payload.enabled is not None:
        doc.enabled = payload.enabled
    if payload.kind is not None:
        new_kind = _check_kind(payload.kind)
        old_kind = doc.kind
        doc.kind = new_kind
        for chunk in (await db.execute(select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id,
                                                                     KnowledgeChunk.kind == old_kind))).scalars().all():
            chunk.kind = new_kind
    if payload.clear_valid_until:
        doc.valid_until = None
    elif payload.valid_until is not None:
        doc.valid_until = payload.valid_until
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="knowledge.updated",
                                  entity_type="knowledge_document", entity_id=doc.id,
                                  metadata=payload.model_dump(exclude_none=True, mode="json"))
    await db.commit()
    return await _doc_out(db, doc)


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(workspace_id: uuid.UUID, doc_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member),
                          user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_role(member.role, CAN_EDIT_CONTENT)
    doc = await _doc_or_404(db, workspace_id, doc_id)
    await db.delete(doc)
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="knowledge.deleted",
                                  entity_type="knowledge_document", entity_id=doc_id, metadata={"title": doc.title})
    await db.commit()


@router.get("/search", response_model=list[SearchHit])
async def search(workspace_id: uuid.UUID, q: str = Query(min_length=2, max_length=200),
                 member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db)):
    hits = await KnowledgeService(db).search(workspace_id, q)
    out = []
    for chunk, doc in hits:
        pos = chunk.content.lower().find(q.lower())
        start = max(0, pos - 80)
        out.append(SearchHit(document_id=doc.id, document_title=doc.title, kind=chunk.kind,
                             snippet=("…" if start else "") + chunk.content[start:start + 240], effective_at=chunk.effective_at))
    return out
