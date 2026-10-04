from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_session, get_current_user, get_db
from app.core.auth import (
    SESSION_COOKIE_NAME,
    create_session,
    read_session_id,
    revoke_all,
    session_max_age,
    sign_session_id,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.models.enums import WorkspaceRole
from app.models.identity import User, UserSession, Workspace, WorkspaceMember
from app.services.audit.service import AuditService
from app.services.security import rate_limit as rl

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger(__name__)

# Used when the email is unknown so a login attempt costs the same Argon2 work
# either way — response timing doesn't reveal whether an account exists.
_DUMMY_HASH = hash_password("timing-equalizer-not-a-real-password")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    full_name: str = Field(default="", max_length=200)
    workspace_name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str


class SessionResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    ip_address: str
    user_agent: str
    current: bool


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{slug or 'workspace'}-{uuid.uuid4().hex[:6]}"


def _set_session_cookie(response: Response, session_id: uuid.UUID) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=sign_session_id(session_id),
        max_age=session_max_age(),
        httponly=True,
        secure=get_settings().is_production,
        samesite="lax",
        path="/",
    )


async def _start_session(db: AsyncSession, request: Request, response: Response, user: User) -> None:
    row = await create_session(
        db, user.id, ip=rl.client_ip(request), user_agent=request.headers.get("user-agent", "")
    )
    _set_session_cookie(response, row.id)


async def _audit_for_user(db: AsyncSession, user: User, action: str, request: Request) -> None:
    memberships = await db.execute(select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id))
    audit = AuditService(db)
    for (workspace_id,) in memberships.all():
        await audit.record(
            workspace_id=workspace_id, actor_user_id=user.id, action=action, entity_type="user",
            entity_id=user.id, metadata={"ip": rl.client_ip(request)},
        )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    await rl.hit_all((rl.REGISTER_PER_IP, rl.client_ip(request)))
    email = payload.email.lower()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        # Generic wording; registration is rate limited per IP to slow enumeration.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unable to create an account with these details.")

    user = User(email=email, hashed_password=hash_password(payload.password), full_name=payload.full_name)
    db.add(user)
    await db.flush()
    workspace = Workspace(name=payload.workspace_name, slug=_slugify(payload.workspace_name))
    db.add(workspace)
    await db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER))
    await AuditService(db).record(
        workspace_id=workspace.id, actor_user_id=user.id, action="workspace.created",
        entity_type="workspace", entity_id=workspace.id, metadata={"name": workspace.name},
    )
    await _start_session(db, request, response, user)
    await db.commit()
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name)


@router.post("/login", response_model=UserResponse)
async def login(payload: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    email = payload.email.lower()
    await rl.hit_all((rl.LOGIN_PER_IP, rl.client_ip(request)), (rl.LOGIN_PER_ACCOUNT, email))

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    password_ok = verify_password(payload.password, user.hashed_password if user else _DUMMY_HASH)
    if not user or not password_ok or not user.is_active:
        if user:
            await _audit_for_user(db, user, "auth.login_failed", request)
            await db.commit()
        log.info("login_failed", known_account=bool(user))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    await rl.reset(rl.LOGIN_PER_ACCOUNT, email)
    await _start_session(db, request, response, user)
    await _audit_for_user(db, user, "auth.login", request)
    await db.commit()
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
):
    session_id = read_session_id(session_token) if session_token else None
    if session_id:
        row = await db.get(UserSession, session_id)
        if row and row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)
            await db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name)


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    current: UserSession = Depends(get_current_session), db: AsyncSession = Depends(get_db)
):
    now = datetime.now(UTC)
    result = await db.execute(
        select(UserSession)
        .where(UserSession.user_id == current.user_id, UserSession.revoked_at.is_(None), UserSession.expires_at > now)
        .order_by(UserSession.last_seen_at.desc())
    )
    return [
        SessionResponse(
            id=s.id, created_at=s.created_at, last_seen_at=s.last_seen_at, expires_at=s.expires_at,
            ip_address=s.ip_address, user_agent=s.user_agent, current=s.id == current.id,
        )
        for s in result.scalars().all()
    ]


@router.post("/sessions/revoke-others", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_other_sessions(
    request: Request, current: UserSession = Depends(get_current_session), db: AsyncSession = Depends(get_db)
):
    await revoke_all(db, current.user_id, except_id=current.id)
    user = await db.get(User, current.user_id)
    await _audit_for_user(db, user, "auth.sessions_revoked", request)
    await db.commit()
