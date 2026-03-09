"""User management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from satt.auth import require_auth
from satt.database import get_db
from satt.models import User
from sv_common.auth.passwords import hash_password, verify_password

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /api/users  (admin only)
# ---------------------------------------------------------------------------


@router.get("/users")
async def list_users(
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    if not _user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await db.execute(select(User).order_by(User.created_at))
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "isAdmin": u.is_admin,
            "isActive": u.is_active,
            "createdAt": u.created_at.isoformat(),
        }
        for u in users
    ]


# ---------------------------------------------------------------------------
# PUT /api/users/me/password  (any authenticated user)
# ---------------------------------------------------------------------------


class ChangePasswordRequest(BaseModel):
    currentPassword: str
    newPassword: str


@router.put("/users/me/password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="Cannot change password for this session type")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(body.currentPassword, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    if len(body.newPassword) < 8:
        raise HTTPException(status_code=422, detail="New password must be at least 8 characters")

    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(password_hash=hash_password(body.newPassword))
    )
    await db.flush()
    return {"ok": True}


# ---------------------------------------------------------------------------
# POST /api/users/{user_id}/reset-password  (admin only)
# ---------------------------------------------------------------------------


class ResetPasswordRequest(BaseModel):
    newPassword: str


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    body: ResetPasswordRequest,
    current_user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    if len(body.newPassword) < 8:
        raise HTTPException(status_code=422, detail="New password must be at least 8 characters")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(password_hash=hash_password(body.newPassword))
    )
    await db.flush()
    return {"ok": True}
