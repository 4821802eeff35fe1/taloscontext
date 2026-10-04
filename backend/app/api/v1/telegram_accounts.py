from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_workspace_member
from app.api.v1.jobs import JobResponse
from app.core.rbac import CAN_MANAGE_TELEGRAM, require_role
from app.models.enums import JobType
from app.models.identity import User, WorkspaceMember
from app.models.telegram import TelegramAccount, TelegramChannel
from app.services.audit.service import AuditService
from app.services.jobs.service import JobService, dispatch
from app.services.realtime.events import publish_event
from app.services.security import rate_limit as rl
from app.services.telegram.account_service import TelegramAccountService
from app.services.telegram.auth_flow import (
    AuthFlowError,
    AuthFlowState,
    TelegramAuthFlowService,
    public_view,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/telegram", tags=["telegram-accounts"])


class AccountResponse(BaseModel):
    id: uuid.UUID
    phone_masked: str
    status: str
    first_name: str
    last_name: str
    username: str | None
    last_error: str | None
    flood_wait_until: datetime | None
    last_heartbeat_at: datetime | None
    channel_count: int = 0

    @classmethod
    def from_model(cls, a: TelegramAccount, channel_count: int = 0) -> AccountResponse:
        return cls(
            id=a.id, phone_masked=a.phone_masked, status=a.status.value,
            first_name=a.first_name, last_name=a.last_name, username=a.username, last_error=a.last_error,
            flood_wait_until=a.flood_wait_until, last_heartbeat_at=a.last_heartbeat_at,
            channel_count=channel_count,
        )


class AuthFlowResponse(BaseModel):
    flow_id: str
    state: str
    phone_masked: str
    expires_at: str
    error: str | None = None
    account_id: str | None = None
    attempts_left: int
    refresh_job_id: uuid.UUID | None = None


class StartAuthRequest(BaseModel):
    phone: str = Field(min_length=6, max_length=24)
    account_id: uuid.UUID | None = None  # set to reconnect an existing account


class CodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=12)


class PasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


async def _flow_response(
    db: AsyncSession, workspace_id: uuid.UUID, user: User, flow: dict
) -> AuthFlowResponse:
    """Commits; on completion audits and kicks off channel import."""
    refresh_job_id = None
    if flow["state"] == AuthFlowState.COMPLETED and flow.get("result_account_id"):
        account_id = uuid.UUID(flow["result_account_id"])
        await AuditService(db).record(
            workspace_id=workspace_id, actor_user_id=user.id, action="telegram.account_connected",
            entity_type="telegram_account", entity_id=account_id, metadata={"phone": flow["phone_masked"]},
        )
        job = await JobService(db).create(
            workspace_id=workspace_id, job_type=JobType.TELEGRAM_REFRESH_CHANNELS,
            payload={"account_id": str(account_id)}, entity_type="telegram_account", entity_id=account_id,
            summary=f"Import channels for {flow['phone_masked']}", created_by_user_id=user.id, max_attempts=3,
        )
        await db.commit()
        await dispatch(job)
        refresh_job_id = job.id
    else:
        await db.commit()
    await publish_event(workspace_id, "telegram.auth.updated", {"flow_id": flow["flow_id"], "state": flow["state"]})
    return AuthFlowResponse(**public_view(flow), refresh_job_id=refresh_job_id)


def _raise(exc: AuthFlowError) -> None:
    raise HTTPException(exc.status_code, str(exc)) from exc


@router.get("/accounts", response_model=list[AccountResponse])
async def list_accounts(
    workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db)
):
    accounts = (
        await db.execute(
            select(TelegramAccount).where(TelegramAccount.workspace_id == workspace_id).order_by(TelegramAccount.created_at)
        )
    ).scalars().all()
    counts = dict(
        (
            await db.execute(
                select(TelegramChannel.account_id, func.count())
                .where(TelegramChannel.workspace_id == workspace_id)
                .group_by(TelegramChannel.account_id)
            )
        ).all()
    )
    return [AccountResponse.from_model(a, counts.get(a.id, 0)) for a in accounts]


@router.post("/auth/start", response_model=AuthFlowResponse, status_code=status.HTTP_201_CREATED)
async def start_auth(
    workspace_id: uuid.UUID, payload: StartAuthRequest, request: Request,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_MANAGE_TELEGRAM)
    await rl.hit_all((rl.TG_START_PER_WORKSPACE, str(workspace_id)), (rl.TG_CODE_PER_IP, rl.client_ip(request)))
    try:
        flow = await TelegramAuthFlowService(db).start(
            workspace_id=workspace_id, user_id=user.id, phone=payload.phone, account_id=payload.account_id
        )
    except AuthFlowError as exc:
        _raise(exc)
    return await _flow_response(db, workspace_id, user, flow)


@router.get("/auth/{flow_id}", response_model=AuthFlowResponse)
async def get_auth(
    workspace_id: uuid.UUID, flow_id: str,
    member: WorkspaceMember = Depends(get_workspace_member), db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_MANAGE_TELEGRAM)
    try:
        flow = await TelegramAuthFlowService(db).get(workspace_id=workspace_id, flow_id=flow_id)
    except AuthFlowError as exc:
        _raise(exc)
    return AuthFlowResponse(**public_view(flow))


@router.post("/auth/{flow_id}/code", response_model=AuthFlowResponse)
async def submit_code(
    workspace_id: uuid.UUID, flow_id: str, payload: CodeRequest, request: Request,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_MANAGE_TELEGRAM)
    await rl.hit_all((rl.TG_CODE_PER_FLOW, flow_id), (rl.TG_CODE_PER_IP, rl.client_ip(request)))
    try:
        flow = await TelegramAuthFlowService(db).submit_code(workspace_id=workspace_id, flow_id=flow_id, code=payload.code)
    except AuthFlowError as exc:
        _raise(exc)
    return await _flow_response(db, workspace_id, user, flow)


@router.post("/auth/{flow_id}/password", response_model=AuthFlowResponse)
async def submit_password(
    workspace_id: uuid.UUID, flow_id: str, payload: PasswordRequest, request: Request,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_MANAGE_TELEGRAM)
    await rl.hit_all((rl.TG_PASSWORD_PER_FLOW, flow_id), (rl.TG_PASSWORD_PER_IP, rl.client_ip(request)))
    try:
        flow = await TelegramAuthFlowService(db).submit_password(
            workspace_id=workspace_id, flow_id=flow_id, password=payload.password
        )
    except AuthFlowError as exc:
        _raise(exc)
    return await _flow_response(db, workspace_id, user, flow)


async def _account_or_404(db: AsyncSession, workspace_id: uuid.UUID, account_id: uuid.UUID) -> TelegramAccount:
    account = await db.get(TelegramAccount, account_id)
    if account is None or account.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Telegram account not found")
    return account


@router.post("/accounts/{account_id}/refresh-channels", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def refresh_channels(
    workspace_id: uuid.UUID, account_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_MANAGE_TELEGRAM)
    account = await _account_or_404(db, workspace_id, account_id)
    service = JobService(db)
    existing = await service.active_for_entity("telegram_account", account.id)
    if existing and existing.job_type == JobType.TELEGRAM_REFRESH_CHANNELS:
        return JobResponse.from_model(existing)
    job = await service.create(
        workspace_id=workspace_id, job_type=JobType.TELEGRAM_REFRESH_CHANNELS,
        payload={"account_id": str(account.id)}, entity_type="telegram_account", entity_id=account.id,
        summary=f"Import channels for {account.phone_masked}", created_by_user_id=user.id, max_attempts=3,
    )
    await db.commit()
    await dispatch(job)
    await db.refresh(job)
    return JobResponse.from_model(job)


@router.post("/accounts/{account_id}/disconnect", response_model=AccountResponse)
async def disconnect(
    workspace_id: uuid.UUID, account_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_MANAGE_TELEGRAM)
    try:
        account = await TelegramAccountService(db).disconnect(workspace_id=workspace_id, account_id=account_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    await AuditService(db).record(
        workspace_id=workspace_id, actor_user_id=user.id, action="telegram.account_disconnected",
        entity_type="telegram_account", entity_id=account.id,
    )
    await db.commit()
    await publish_event(workspace_id, "telegram.account.health_changed", {"account_id": str(account.id), "status": account.status.value})
    return AccountResponse.from_model(account)


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    workspace_id: uuid.UUID, account_id: uuid.UUID,
    member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role(member.role, CAN_MANAGE_TELEGRAM)
    try:
        account = await TelegramAccountService(db)._get(workspace_id, account_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    masked = account.phone_masked
    await TelegramAccountService(db).delete(workspace_id=workspace_id, account_id=account_id)
    await AuditService(db).record(
        workspace_id=workspace_id, actor_user_id=user.id, action="telegram.account_removed",
        entity_type="telegram_account", entity_id=account_id, metadata={"phone": masked},
    )
    await db.commit()
