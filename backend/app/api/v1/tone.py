from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_workspace_member
from app.core.errors import ApiError
from app.core.rbac import CAN_EDIT_CONTENT, CAN_MANAGE_SETTINGS, require_role
from app.models.content import ContentSeries
from app.models.identity import User, WorkspaceMember
from app.models.knowledge import ToneOfVoiceProfile
from app.models.telegram import TelegramChannel
from app.services.audit.service import AuditService
from app.services.settings.service import get_workspace_settings

router = APIRouter(prefix="/workspaces/{workspace_id}/tone-profiles", tags=["tone"])

_LIST_FIELDS = ("allowed_vocabulary", "forbidden_vocabulary", "cliches_blacklist", "good_examples", "bad_examples")


class ToneIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    language: str = Field(default="ru", max_length=32)
    addressing: str = Field(default="", max_length=50)
    formality: str = Field(default="", max_length=50)
    emoji_policy: str = Field(default="minimal", max_length=50)
    headline_style: str = Field(default="", max_length=100)
    paragraph_style: str = Field(default="", max_length=100)
    average_length: str = Field(default="medium", max_length=50)
    cta_style: str = Field(default="", max_length=100)
    allowed_vocabulary: list[str] = Field(default_factory=list, max_length=200)
    forbidden_vocabulary: list[str] = Field(default_factory=list, max_length=200)
    cliches_blacklist: list[str] = Field(default_factory=list, max_length=200)
    good_examples: list[str] = Field(default_factory=list, max_length=20)
    bad_examples: list[str] = Field(default_factory=list, max_length=20)


class ToneOut(ToneIn):
    id: uuid.UUID
    is_workspace_default: bool
    channel_count: int
    series_count: int
    updated_at: datetime


def _apply(p: ToneOfVoiceProfile, data: ToneIn) -> None:
    for field, value in data.model_dump().items():
        if field in _LIST_FIELDS:
            clean = [v.strip() for v in value if v and v.strip()]
            setattr(p, f"{field}_json", json.dumps(clean, ensure_ascii=False))
        else:
            setattr(p, field, value)


async def _out(db: AsyncSession, p: ToneOfVoiceProfile, default_id: uuid.UUID | None) -> ToneOut:
    channels = await db.scalar(select(func.count()).select_from(TelegramChannel).where(TelegramChannel.tone_profile_id == p.id))
    series = await db.scalar(select(func.count()).select_from(ContentSeries).where(ContentSeries.tone_profile_id == p.id))
    data = {f: getattr(p, f) for f in ToneIn.model_fields if f not in _LIST_FIELDS}
    for f in _LIST_FIELDS:
        data[f] = json.loads(getattr(p, f"{f}_json") or "[]")
    return ToneOut(**data, id=p.id, is_workspace_default=p.id == default_id, channel_count=channels or 0,
                   series_count=series or 0, updated_at=p.updated_at)


async def _get(db, workspace_id, profile_id) -> ToneOfVoiceProfile:
    p = await db.get(ToneOfVoiceProfile, profile_id)
    if p is None or p.workspace_id != workspace_id:
        raise ApiError(404, "TONE_PROFILE_NOT_FOUND", "Tone profile not found")
    return p


@router.get("", response_model=list[ToneOut])
async def list_profiles(workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member),
                        db: AsyncSession = Depends(get_db)):
    settings = await get_workspace_settings(db, workspace_id)
    await db.commit()
    profiles = (await db.execute(select(ToneOfVoiceProfile).where(ToneOfVoiceProfile.workspace_id == workspace_id)
                                 .order_by(ToneOfVoiceProfile.name))).scalars().all()
    return [await _out(db, p, settings.default_tone_profile_id) for p in profiles]


@router.post("", response_model=ToneOut, status_code=status.HTTP_201_CREATED)
async def create_profile(workspace_id: uuid.UUID, payload: ToneIn, member: WorkspaceMember = Depends(get_workspace_member),
                         user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_role(member.role, CAN_EDIT_CONTENT)
    p = ToneOfVoiceProfile(workspace_id=workspace_id, name=payload.name)
    _apply(p, payload)
    db.add(p)
    await db.flush()
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="tone.created",
                                  entity_type="tone_profile", entity_id=p.id, metadata={"name": p.name})
    settings = await get_workspace_settings(db, workspace_id)
    await db.commit()
    return await _out(db, p, settings.default_tone_profile_id)


@router.put("/{profile_id}", response_model=ToneOut)
async def update_profile(workspace_id: uuid.UUID, profile_id: uuid.UUID, payload: ToneIn,
                         member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    require_role(member.role, CAN_EDIT_CONTENT)
    p = await _get(db, workspace_id, profile_id)
    _apply(p, payload)
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="tone.updated",
                                  entity_type="tone_profile", entity_id=p.id, metadata={"name": p.name})
    settings = await get_workspace_settings(db, workspace_id)
    await db.commit()
    return await _out(db, p, settings.default_tone_profile_id)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(workspace_id: uuid.UUID, profile_id: uuid.UUID,
                         member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    require_role(member.role, CAN_EDIT_CONTENT)
    p = await _get(db, workspace_id, profile_id)
    await db.delete(p)  # FKs are ON DELETE SET NULL: channels/series fall back to the next level
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="tone.deleted",
                                  entity_type="tone_profile", entity_id=profile_id, metadata={"name": p.name})
    await db.commit()


@router.post("/{profile_id}/make-default", response_model=ToneOut)
async def make_default(workspace_id: uuid.UUID, profile_id: uuid.UUID,
                       member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    require_role(member.role, CAN_MANAGE_SETTINGS)
    p = await _get(db, workspace_id, profile_id)
    settings = await get_workspace_settings(db, workspace_id)
    settings.default_tone_profile_id = p.id
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="tone.workspace_default_set",
                                  entity_type="tone_profile", entity_id=p.id, metadata={"name": p.name})
    await db.commit()
    return await _out(db, p, p.id)
