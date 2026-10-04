from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_workspace_member
from app.core.rbac import CAN_MANAGE_MEMBERS, require_role
from app.models.enums import WorkspaceRole
from app.models.identity import User, Workspace, WorkspaceMember
from app.services.audit.service import AuditService

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: str


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
    )
    return [
        WorkspaceResponse(id=ws.id, name=ws.name, slug=ws.slug, role=role.value)
        for ws, role in result.all()
    ]


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str


class MemberIn(BaseModel):
    email: str
    role: WorkspaceRole = WorkspaceRole.VIEWER


class RoleIn(BaseModel):
    role: WorkspaceRole


async def _members(db: AsyncSession, workspace_id: uuid.UUID) -> list[MemberOut]:
    rows = await db.execute(
        select(User, WorkspaceMember.role).join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.workspace_id == workspace_id).order_by(User.email)
    )
    return [MemberOut(user_id=u.id, email=u.email, full_name=u.full_name, role=r.value) for u, r in rows.all()]


@router.get("/{workspace_id}/members", response_model=list[MemberOut])
async def list_members(workspace_id: uuid.UUID, member: WorkspaceMember = Depends(get_workspace_member),
                       db: AsyncSession = Depends(get_db)):
    return await _members(db, workspace_id)


@router.post("/{workspace_id}/members", response_model=list[MemberOut], status_code=status.HTTP_201_CREATED)
async def add_member(workspace_id: uuid.UUID, payload: MemberIn, member: WorkspaceMember = Depends(get_workspace_member),
                     user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Adds an existing ChannelOS user. (No e-mail invitations in v0.2.)"""
    require_role(member.role, CAN_MANAGE_MEMBERS)
    target = (await db.execute(select(User).where(User.email == payload.email.lower()))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No ChannelOS user with this e-mail. Ask them to sign up first.")
    exists = (await db.execute(select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == target.id))).scalar_one_or_none()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already a member")
    db.add(WorkspaceMember(workspace_id=workspace_id, user_id=target.id, role=payload.role))
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="member.added",
                                  entity_type="user", entity_id=target.id, metadata={"role": payload.role.value})
    await db.commit()
    return await _members(db, workspace_id)


@router.patch("/{workspace_id}/members/{user_id}", response_model=list[MemberOut])
async def change_role(workspace_id: uuid.UUID, user_id: uuid.UUID, payload: RoleIn,
                      member: WorkspaceMember = Depends(get_workspace_member), user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    require_role(member.role, CAN_MANAGE_MEMBERS)
    target = (await db.execute(select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    if target.role == WorkspaceRole.OWNER and payload.role != WorkspaceRole.OWNER:
        owners = (await db.execute(select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.role == WorkspaceRole.OWNER))).scalars().all()
        if len(owners) <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "A workspace needs at least one owner.")
    before = target.role.value
    target.role = payload.role
    await AuditService(db).record(workspace_id=workspace_id, actor_user_id=user.id, action="member.role_changed",
                                  entity_type="user", entity_id=user_id,
                                  metadata={"from": before, "to": payload.role.value})
    await db.commit()
    return await _members(db, workspace_id)
