from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.identity import User, Workspace, WorkspaceMember

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
