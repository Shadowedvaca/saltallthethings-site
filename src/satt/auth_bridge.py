"""Auth dependency: JWT Bearer or temporary X-Auth plaintext bridge.

The X-Auth bridge is removed in Phase 4. Until then, both mechanisms are
accepted so we can test Phase 2/3 without requiring the frontend to be
updated first.
"""

from __future__ import annotations

import jwt
from fastapi import Header, HTTPException

from satt.auth import decode_access_token
from satt.config import get_settings
from sv_common.auth.passwords import verify_password


async def require_auth(
    authorization: str | None = Header(None),
    x_auth: str | None = Header(None, alias="X-Auth"),
) -> dict:
    """FastAPI dependency: validate JWT or X-Auth bridge. Returns token payload."""

    # 1. Try JWT from Authorization: Bearer <token>
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        try:
            return decode_access_token(token)
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")

    # 2. Fall back to X-Auth plaintext password bridge
    if x_auth:
        settings = get_settings()
        if settings.admin_password_hash and verify_password(
            x_auth, settings.admin_password_hash
        ):
            return {"username": "bridge", "is_admin": True}
        raise HTTPException(status_code=401, detail="Invalid X-Auth credential")

    raise HTTPException(status_code=401, detail="Authentication required")
