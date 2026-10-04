from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_workspace_member
from app.core.rbac import CAN_MANAGE_TELEGRAM, require_role
from app.models.identity import WorkspaceMember
from app.models.telegram import ChannelSet, ChannelSetMember, TelegramChannel

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["channels"])


class ChannelResponse(BaseModel):
    id: uuid.UUID
    title: str
    username: str | None
    can_post: bool
    health: str
    subscriber_count: int | None
    autopilot_enabled: bool
    default_cta_key: str | None


class ChannelUpdateRequest(BaseModel):
    autopilot_enabled: bool | None = None
    default_cta_key: str | None = None
    timezone: str | None = None
    tone_profile_id: uuid.UUID | None = None


class ChannelSetCreateRequest(BaseModel):
    name: str
    description: str = ""
    mode: str = "EXACT"
    channel_ids: list[uuid.UUID] = []


class ChannelSetResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    mode: str
    autopilot_enabled: bool
    member_count: int


def _to_channel_response(c: TelegramChannel) -> ChannelResponse:
    return ChannelResponse(
        id=c.id, title=c.title, username=c.username, can_post=c.can_post, health=c.health.value,
        subscriber_count=c.subscriber_count, autopilot_enabled=c.autopilot_enabled,
        default_cta_key=c.default_cta_key,
    )


@router.get("/channels", response_model=list[ChannelResponse])
async def list_channels(
    workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(TelegramChannel).where(TelegramChannel.workspace_id == workspace_id))
    return [_to_channel_response(c) for c in result.scalars().all()]


@router.patch("/channels/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    workspace_id: uuid.UUID,
    channel_id: uuid.UUID,
    payload: ChannelUpdateRequest,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_MANAGE_TELEGRAM)
    channel = await db.get(TelegramChannel, channel_id)
    if not channel or channel.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(channel, field, value)
    await db.commit()
    return _to_channel_response(channel)


@router.get("/channel-sets", response_model=list[ChannelSetResponse])
async def list_channel_sets(
    workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(ChannelSet).where(ChannelSet.workspace_id == workspace_id))
    sets = result.scalars().all()
    responses = []
    for s in sets:
        count_result = await db.execute(
            select(ChannelSetMember).where(ChannelSetMember.channel_set_id == s.id)
        )
        responses.append(
            ChannelSetResponse(
                id=s.id, name=s.name, description=s.description, mode=s.mode.value,
                autopilot_enabled=s.autopilot_enabled, member_count=len(count_result.all()),
            )
        )
    return responses


@router.post("/channel-sets", response_model=ChannelSetResponse, status_code=status.HTTP_201_CREATED)
async def create_channel_set(
    workspace_id: uuid.UUID,
    payload: ChannelSetCreateRequest,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: AsyncSession = Depends(get_db),
):
    from app.models.enums import ChannelSetMode

    require_role(member.role, CAN_MANAGE_TELEGRAM)
    if payload.channel_ids:
        owned = await db.execute(
            select(TelegramChannel.id).where(
                TelegramChannel.id.in_(payload.channel_ids), TelegramChannel.workspace_id == workspace_id
            )
        )
        if len(owned.all()) != len(set(payload.channel_ids)):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "One or more channels do not belong to this workspace")
    channel_set = ChannelSet(
        workspace_id=workspace_id, name=payload.name, description=payload.description,
        mode=ChannelSetMode(payload.mode),
    )
    db.add(channel_set)
    await db.flush()
    for channel_id in payload.channel_ids:
        db.add(ChannelSetMember(channel_set_id=channel_set.id, channel_id=channel_id))
    await db.commit()
    return ChannelSetResponse(
        id=channel_set.id, name=channel_set.name, description=channel_set.description,
        mode=channel_set.mode.value, autopilot_enabled=channel_set.autopilot_enabled,
        member_count=len(payload.channel_ids),
    )
