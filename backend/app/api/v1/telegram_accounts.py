from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_workspace_member
from app.core.rbac import CAN_MANAGE_TELEGRAM, require_role
from app.models.identity import WorkspaceMember
from app.models.telegram import TelegramAccount, TelegramChannel
from app.services.telegram.account_service import TelegramAccountService

router = APIRouter(prefix="/workspaces/{workspace_id}/telegram/accounts", tags=["telegram-accounts"])


class AccountResponse(BaseModel):
    id: uuid.UUID
    phone_masked: str
    status: str
    first_name: str
    last_name: str
    username: str | None
    last_error: str | None

    @classmethod
    def from_model(cls, a: TelegramAccount) -> AccountResponse:
        return cls(
            id=a.id, phone_masked=a.phone_masked, status=a.status.value,
            first_name=a.first_name, last_name=a.last_name, username=a.username, last_error=a.last_error,
        )


class ChannelResponse(BaseModel):
    id: uuid.UUID
    title: str
    username: str | None
    can_post: bool
    health: str
    subscriber_count: int | None

    @classmethod
    def from_model(cls, c: TelegramChannel) -> ChannelResponse:
        return cls(
            id=c.id, title=c.title, username=c.username, can_post=c.can_post,
            health=c.health.value, subscriber_count=c.subscriber_count,
        )


class StartLoginRequest(BaseModel):
    phone: str


class SubmitCodeRequest(BaseModel):
    code: str


class Submit2FARequest(BaseModel):
    password: str


@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(TelegramAccount).where(TelegramAccount.workspace_id == workspace_id))
    return [AccountResponse.from_model(a) for a in result.scalars().all()]


@router.post("/login", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def start_login(
    workspace_id: uuid.UUID,
    payload: StartLoginRequest,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_MANAGE_TELEGRAM)
    service = TelegramAccountService(db)
    account = await service.start_login(workspace_id=workspace_id, phone=payload.phone)
    await db.commit()
    return AccountResponse.from_model(account)


@router.post("/{account_id}/verify", response_model=AccountResponse)
async def submit_code(
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    payload: SubmitCodeRequest,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_MANAGE_TELEGRAM)
    service = TelegramAccountService(db)
    try:
        account = await service.submit_code(workspace_id=workspace_id, account_id=account_id, code=payload.code)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await db.commit()
    return AccountResponse.from_model(account)


@router.post("/{account_id}/2fa", response_model=AccountResponse)
async def submit_2fa(
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    payload: Submit2FARequest,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_MANAGE_TELEGRAM)
    service = TelegramAccountService(db)
    try:
        account = await service.submit_2fa(workspace_id=workspace_id, account_id=account_id, password=payload.password)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await db.commit()
    return AccountResponse.from_model(account)


@router.post("/{account_id}/channels", response_model=list[ChannelResponse])
async def refresh_channels(
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_MANAGE_TELEGRAM)
    service = TelegramAccountService(db)
    try:
        channels = await service.refresh_channels(workspace_id=workspace_id, account_id=account_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await db.commit()
    return [ChannelResponse.from_model(c) for c in channels]


@router.post("/{account_id}/disconnect", response_model=AccountResponse)
async def disconnect(
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_MANAGE_TELEGRAM)
    service = TelegramAccountService(db)
    try:
        account = await service.disconnect(workspace_id=workspace_id, account_id=account_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    await db.commit()
    return AccountResponse.from_model(account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_MANAGE_TELEGRAM)
    service = TelegramAccountService(db)
    try:
        await service.delete(workspace_id=workspace_id, account_id=account_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    await db.commit()
