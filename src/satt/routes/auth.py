"""Auth routes: login and register."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from satt.auth import (
    consume_invite_code,
    create_access_token,
    get_user_by_username,
)
from satt.database import get_db
from satt.models import User
from sv_common.auth.passwords import hash_password, verify_password

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> dict:
    user = await get_user_by_username(db, body.username)
    if user is None or not user.is_active or not verify_password(
        body.password, user.password_hash
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(
        user_id=user.id, username=user.username, is_admin=user.is_admin
    )
    return {"token": token, "username": user.username, "isAdmin": user.is_admin}


# ---------------------------------------------------------------------------
# POST /api/auth/register
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    username: str
    password: str
    inviteCode: str


@router.post("/auth/register", status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> dict:
    # Validate invite code first
    invite = await consume_invite_code(db, body.inviteCode)  # raises ValueError if invalid
    _ = invite  # noqa: used for side-effect (mark consumed)

    # Check username not taken
    existing = await get_user_by_username(db, body.username)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Username already taken")

    username = body.username.lower().strip()
    user = User(
        username=username,
        password_hash=hash_password(body.password),
        is_admin=False,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()

    token = create_access_token(
        user_id=user.id, username=user.username, is_admin=user.is_admin
    )
    return {"token": token, "username": user.username, "isAdmin": user.is_admin}
