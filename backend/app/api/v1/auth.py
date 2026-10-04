from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.auth import SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS, create_session_token
from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.models.enums import WorkspaceRole
from app.models.identity import User, Workspace, WorkspaceMember

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""
    workspace_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or f"workspace-{uuid.uuid4().hex[:8]}"


def _set_session_cookie(response: Response, user_id: uuid.UUID) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(user_id),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(email=payload.email, hashed_password=hash_password(payload.password), full_name=payload.full_name)
    db.add(user)
    await db.flush()

    workspace = Workspace(name=payload.workspace_name, slug=_slugify(payload.workspace_name))
    db.add(workspace)
    await db.flush()

    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER))
    await db.commit()

    _set_session_cookie(response, user.id)
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name)


@router.post("/login", response_model=UserResponse)
async def login(payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    _set_session_cookie(response, user.id)
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name)
