from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_workspace_member
from app.core.rbac import CAN_EDIT_CONTENT, require_role
from app.models.identity import WorkspaceMember
from app.models.media import MediaAsset
from app.services.media.service import MAX_UPLOAD_BYTES, MediaService, UnsupportedMediaError
from app.services.media.storage import MediaStorage

router = APIRouter(prefix="/workspaces/{workspace_id}/media", tags=["media"])


class MediaResponse(BaseModel):
    id: uuid.UUID
    mime_type: str
    width: int | None
    height: int | None
    size_bytes: int
    status: str
    url: str


def _to_response(asset: MediaAsset) -> MediaResponse:
    # Served through the backend (membership-checked) rather than a presigned
    # S3 URL: the S3 endpoint is often an internal hostname (minio:9000 in
    # compose) that browsers can't reach, and this keeps media access behind RBAC.
    return MediaResponse(
        id=asset.id, mime_type=asset.mime_type, width=asset.width, height=asset.height,
        size_bytes=asset.size_bytes, status=asset.status.value,
        url=f"/api/v1/workspaces/{asset.workspace_id}/media/{asset.id}/content",
    )


@router.get("", response_model=list[MediaResponse])
async def list_media(
    workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(MediaAsset).where(MediaAsset.workspace_id == workspace_id).order_by(MediaAsset.created_at.desc())
    )
    return [_to_response(a) for a in result.scalars().all()]


@router.post("/upload", response_model=MediaResponse, status_code=status.HTTP_201_CREATED)
async def upload(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    member: WorkspaceMember = Depends(get_workspace_member),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_EDIT_CONTENT)
    data = await file.read(MAX_UPLOAD_BYTES + 1)  # bounded read; service rejects >limit
    storage = MediaStorage()
    service = MediaService(db, storage)
    try:
        asset = await service.upload(workspace_id=workspace_id, data=data, original_filename=file.filename or "upload")
    except UnsupportedMediaError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    await db.commit()
    return _to_response(asset)


@router.get("/{media_id}/content")
async def media_content(
    workspace_id: uuid.UUID, media_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    asset = await db.get(MediaAsset, media_id)
    if not asset or asset.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")
    data = await MediaStorage().get_object_bytes(asset.bucket, asset.object_key)
    return Response(
        content=data, media_type=asset.mime_type,
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )
