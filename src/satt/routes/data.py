"""Private CRUD routes — all require authentication."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from satt.auth_bridge import require_auth
from satt.crud import (
    get_assignments,
    get_config,
    get_ideas,
    get_jokes,
    get_show_slots,
    replace_assignments,
    replace_ideas,
    replace_jokes,
    replace_show_slots,
    save_config,
)
from satt.database import get_db

router = APIRouter()

_ALLOWED_KEYS = {"config", "ideas", "jokes", "showSlots", "assignments"}


# ---------------------------------------------------------------------------
# GET /api/export
# ---------------------------------------------------------------------------


@router.get("/export")
async def export_all(
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    config, ideas, jokes, show_slots, assignments = (
        await get_config(db),
        await get_ideas(db),
        await get_jokes(db),
        await get_show_slots(db),
        await get_assignments(db),
    )
    return {
        "config": config,
        "ideas": ideas,
        "jokes": jokes,
        "showSlots": show_slots,
        "assignments": assignments,
    }


# ---------------------------------------------------------------------------
# GET /api/data/:key
# ---------------------------------------------------------------------------


@router.get("/data/{key}")
async def get_data(
    key: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if key not in _ALLOWED_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown key: {key!r}")

    if key == "config":
        return await get_config(db)
    if key == "ideas":
        return await get_ideas(db)
    if key == "jokes":
        return await get_jokes(db)
    if key == "showSlots":
        return await get_show_slots(db)
    if key == "assignments":
        return await get_assignments(db)


# ---------------------------------------------------------------------------
# PUT /api/data/:key
# ---------------------------------------------------------------------------


@router.put("/data/{key}")
async def put_data(
    key: str,
    body: Any = Body(...),
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if key not in _ALLOWED_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown key: {key!r}")

    if key == "config":
        if not isinstance(body, dict):
            raise HTTPException(status_code=422, detail="config must be an object")
        await save_config(db, body)
    elif key == "ideas":
        if not isinstance(body, list):
            raise HTTPException(status_code=422, detail="ideas must be an array")
        await replace_ideas(db, body)
    elif key == "jokes":
        if not isinstance(body, list):
            raise HTTPException(status_code=422, detail="jokes must be an array")
        await replace_jokes(db, body)
    elif key == "showSlots":
        if not isinstance(body, list):
            raise HTTPException(status_code=422, detail="showSlots must be an array")
        await replace_show_slots(db, body)
    elif key == "assignments":
        if not isinstance(body, dict):
            raise HTTPException(status_code=422, detail="assignments must be an object")
        await replace_assignments(db, body)

    return {"ok": True}


# ---------------------------------------------------------------------------
# PUT /api/import
# ---------------------------------------------------------------------------


@router.put("/import")
async def bulk_import(
    body: dict,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if "config" in body:
        await save_config(db, body["config"])
    if "ideas" in body:
        await replace_ideas(db, body["ideas"])
    if "jokes" in body:
        await replace_jokes(db, body["jokes"])
    if "showSlots" in body:
        await replace_show_slots(db, body["showSlots"])
    if "assignments" in body:
        await replace_assignments(db, body["assignments"])
    return {"ok": True}
