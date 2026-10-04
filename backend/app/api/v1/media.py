from __future__ import annotations

import base64
import uuid
from datetime import datetime
from decimal import Decimal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_workspace_member
from app.api.v1.jobs import JobResponse
from app.core.rbac import CAN_EDIT_CONTENT, require_role
from app.models.content import ContentItem
from app.models.enums import JobType, MediaStatus
from app.models.identity import User, WorkspaceMember
from app.models.media import MediaAsset, MediaGeneration
from app.services.ai.base import ImageProviderStatus
from app.services.ai.factory import get_image_provider
from app.services.audit.service import AuditService
from app.services.jobs.service import JobService, dispatch
from app.services.media.service import MAX_UPLOAD_BYTES, MediaService, UnsupportedMediaError
from app.services.media.storage import MediaStorage
from app.services.realtime.events import publish_event

router = APIRouter(prefix="/workspaces/{workspace_id}/media", tags=["media"])

IMAGE_UNAVAILABLE = (
    "Configured Timeweb AI Agent does not expose image generation through the supported programmatic API."
)


class MediaResponse(BaseModel):
    id: uuid.UUID
    mime_type: str
    width: int | None
    height: int | None
    size_bytes: int
    status: str
    source: str  # generated|uploaded
    used: bool
    original_filename: str
    url: str
    created_at: datetime


class MediaDetail(MediaResponse):
    provider: str | None
    model: str | None
    prompt: str | None
    cost_rub: Decimal | None
    checksum_sha256: str
    linked_posts: list[dict]


class MediaPage(BaseModel):
    items: list[MediaResponse]
    next_cursor: str | None


class GenerateImageRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    content_id: uuid.UUID | None = None


def _url(asset: MediaAsset) -> str:
    # Served through the backend (membership-checked) rather than a presigned
    # S3 URL: the S3 endpoint is often an internal hostname (minio:9000 in
    # compose) that browsers can't reach, and this keeps media access behind RBAC.
    return f"/api/v1/workspaces/{asset.workspace_id}/media/{asset.id}/content"


async def _responses(db: AsyncSession, assets: list[MediaAsset]) -> list[MediaResponse]:
    ids = [a.id for a in assets]
    generated = set((await db.execute(select(MediaGeneration.media_asset_id)
                                      .where(MediaGeneration.media_asset_id.in_(ids)))).scalars().all()) if ids else set()
    used = set((await db.execute(select(ContentItem.media_asset_id).where(
        ContentItem.media_asset_id.in_(ids), ContentItem.deleted_at.is_(None)))).scalars().all()) if ids else set()
    return [MediaResponse(
        id=a.id, mime_type=a.mime_type, width=a.width, height=a.height, size_bytes=a.size_bytes,
        status=a.status.value, source="generated" if a.id in generated else "uploaded", used=a.id in used,
        original_filename=a.original_filename, url=_url(a), created_at=a.created_at,
    ) for a in assets]


async def _asset_or_404(db, workspace_id, media_id) -> MediaAsset:
    asset = await db.get(MediaAsset, media_id)
    if not asset or asset.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")
    return asset


@router.get("", response_model=MediaPage)
async def list_media(
    workspace_id: uuid.UUID,
    tab: str = Query(default="all", pattern="^(all|generated|uploaded|used|unused|archived)$"),
    content_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = Query(default=48, ge=1, le=200),
    member: WorkspaceMember = Depends(get_workspace_member),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(MediaAsset).where(MediaAsset.workspace_id == workspace_id)
    is_generated = exists().where(MediaGeneration.media_asset_id == MediaAsset.id)
    is_used = exists().where(ContentItem.media_asset_id == MediaAsset.id, ContentItem.deleted_at.is_(None))
    if tab == "archived":
        stmt = stmt.where(MediaAsset.status == MediaStatus.ARCHIVED)
    else:
        stmt = stmt.where(MediaAsset.status != MediaStatus.ARCHIVED)
        stmt = {"generated": stmt.where(is_generated), "uploaded": stmt.where(~is_generated),
                "used": stmt.where(is_used), "unused": stmt.where(~is_used)}.get(tab, stmt)
    if content_id:
        stmt = stmt.where(exists().where(ContentItem.media_asset_id == MediaAsset.id, ContentItem.id == content_id))
    if cursor:
        try:
            stamp, last = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
            stamp_dt, last_id = datetime.fromisoformat(stamp), uuid.UUID(last)
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid cursor") from exc
        stmt = stmt.where(or_(MediaAsset.created_at < stamp_dt,
                              and_(MediaAsset.created_at == stamp_dt, MediaAsset.id < last_id)))
    rows = (await db.execute(stmt.order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc()).limit(limit + 1))).scalars().all()
    page = list(rows[:limit])
    next_cursor = (base64.urlsafe_b64encode(f"{page[-1].created_at.isoformat()}|{page[-1].id}".encode()).decode()
                   if len(rows) > limit else None)
    return MediaPage(items=await _responses(db, page), next_cursor=next_cursor)


@router.post("/upload", response_model=MediaResponse, status_code=status.HTTP_201_CREATED)
async def upload(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    member: WorkspaceMember = Depends(get_workspace_member),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    data = await file.read(MAX_UPLOAD_BYTES + 1)  # bounded read; service rejects >limit
    service = MediaService(db, MediaStorage())
    try:
        asset = await service.upload(workspace_id=workspace_id, data=data, original_filename=file.filename or "upload")
    except UnsupportedMediaError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="media.uploaded",
                                  entity_type="media", entity_id=asset.id,
                                  metadata={"file": asset.original_filename, "bytes": asset.size_bytes})
    await db.commit()
    await publish_event(workspace_id, "media.created", {"media_id": str(asset.id)})
    return (await _responses(db, [asset]))[0]


@router.get("/image-provider")
async def image_provider_status(workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member)):
    provider = get_image_provider()
    state = await provider.status()
    return {"provider": provider.name, "status": state.value,
            "available": state == ImageProviderStatus.AVAILABLE,
            "message": None if state == ImageProviderStatus.AVAILABLE else IMAGE_UNAVAILABLE,
            "sizes": provider.supports_sizes()}


@router.post("/generate", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_image(
    workspace_id: uuid.UUID, payload: GenerateImageRequest,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    if await get_image_provider().status() != ImageProviderStatus.AVAILABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, IMAGE_UNAVAILABLE)
    if payload.content_id:
        item = await db.get(ContentItem, payload.content_id)
        if item is None or item.workspace_id != workspace_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Content item not found")
    from app.services.costs.service import CostService

    await CostService(db).assert_ai_allowed(workspace_id, Decimal(0))
    job = await JobService(db).create(
        workspace_id=workspace_id, job_type=JobType.AI_GENERATE_IMAGE,
        payload={"prompt": payload.prompt, "content_id": str(payload.content_id) if payload.content_id else None},
        entity_type="content" if payload.content_id else "workspace", entity_id=payload.content_id or workspace_id,
        summary=f"Image: {payload.prompt[:100]}", created_by_user_id=user.id, max_attempts=1,
    )
    await db.commit()
    await dispatch(job)
    await db.refresh(job)
    return JobResponse.from_model(job)


@router.get("/{media_id}", response_model=MediaDetail)
async def media_detail(workspace_id: uuid.UUID, media_id: uuid.UUID,
                       member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db)):
    asset = await _asset_or_404(db, workspace_id, media_id)
    gen = (await db.execute(select(MediaGeneration).where(MediaGeneration.media_asset_id == asset.id))).scalar_one_or_none()
    posts = (await db.execute(select(ContentItem).where(ContentItem.media_asset_id == asset.id,
                                                        ContentItem.deleted_at.is_(None)))).scalars().all()
    base = (await _responses(db, [asset]))[0]
    return MediaDetail(
        **base.model_dump(), provider=gen.provider if gen else None, model=gen.model if gen else None,
        prompt=gen.prompt if gen else None, cost_rub=Decimal(gen.cost_total_rub) if gen else None,
        checksum_sha256=asset.checksum_sha256,
        linked_posts=[{"id": str(p.id), "title": p.title or p.topic or "Untitled", "status": p.status.value} for p in posts],
    )


@router.post("/{media_id}/archive", response_model=MediaResponse)
async def archive_media(workspace_id: uuid.UUID, media_id: uuid.UUID, archived: bool = True,
                        member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    require_role(member.role, CAN_EDIT_CONTENT)
    asset = await _asset_or_404(db, workspace_id, media_id)
    if archived:
        asset.status = MediaStatus.ARCHIVED
    elif asset.status == MediaStatus.ARCHIVED:
        has_gen = await db.scalar(select(exists().where(MediaGeneration.media_asset_id == asset.id)))
        asset.status = MediaStatus.GENERATED if has_gen else MediaStatus.UPLOADED
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id,
                                  action="media.archived" if archived else "media.restored",
                                  entity_type="media", entity_id=asset.id)
    await db.commit()
    return (await _responses(db, [asset]))[0]


@router.get("/{media_id}/content")
async def media_content(
    workspace_id: uuid.UUID, media_id: uuid.UUID, download: bool = False,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    asset = await _asset_or_404(db, workspace_id, media_id)
    data = await MediaStorage().get_object_bytes(asset.bucket, asset.object_key)
    headers = {"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff",
               "Content-Security-Policy": "default-src 'none'; sandbox"}
    if download:
        safe = asset.original_filename or f"{asset.id}"
        headers["Content-Disposition"] = "attachment; filename*=UTF-8''" + quote(safe, safe="")
    return Response(content=data, media_type=asset.mime_type, headers=headers)
