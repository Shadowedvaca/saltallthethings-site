"""Private CRUD routes — all require authentication."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from satt.auth import require_auth
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
_CONFIG_SECRET_KEYS = ("claudeApiKey", "openaiApiKey")


def _public_config(config: dict) -> dict:
    """Return browser-safe config with secret presence flags."""
    public = dict(config)
    for key in _CONFIG_SECRET_KEYS:
        public.pop(key, None)
        public[f"{key}Configured"] = bool(config.get(key))
    return public


def _merge_config_update(
    existing: dict,
    incoming: dict,
    *,
    allow_secret_updates: bool,
) -> dict:
    """Merge a config update while keeping stored API keys server-side."""
    merged = dict(existing)
    update = dict(incoming)

    for key in _CONFIG_SECRET_KEYS:
        value = update.pop(key, None)
        if value is None or value == "":
            continue
        if not isinstance(value, str):
            raise HTTPException(
                status_code=422,
                detail=f"{key} must be a string",
            )
        value = value.strip()
        if not value:
            continue
        if not allow_secret_updates:
            raise HTTPException(
                status_code=403,
                detail="Only administrators may replace AI API keys",
            )
        merged[key] = value

    for key in tuple(update):
        if key.endswith("ApiKeyConfigured"):
            update.pop(key)

    merged.update(update)
    return merged


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
        "config": _public_config(config),
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
        return _public_config(await get_config(db))
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
        existing = await get_config(db)
        merged = _merge_config_update(
            existing,
            body,
            allow_secret_updates=bool(_user.get("is_admin")),
        )
        await save_config(db, merged)
        saved = _public_config(merged)
    elif key == "ideas":
        if not isinstance(body, list):
            raise HTTPException(status_code=422, detail="ideas must be an array")
        await replace_ideas(db, body)
        saved = await get_ideas(db)
    elif key == "jokes":
        if not isinstance(body, list):
            raise HTTPException(status_code=422, detail="jokes must be an array")
        await replace_jokes(db, body)
        saved = await get_jokes(db)
    elif key == "showSlots":
        if not isinstance(body, list):
            raise HTTPException(status_code=422, detail="showSlots must be an array")
        await replace_show_slots(db, body)
        saved = await get_show_slots(db)
    elif key == "assignments":
        if not isinstance(body, dict):
            raise HTTPException(status_code=422, detail="assignments must be an object")
        await replace_assignments(db, body)
        saved = await get_assignments(db)

    return {"ok": True, "data": saved}


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
        if not isinstance(body["config"], dict):
            raise HTTPException(status_code=422, detail="config must be an object")
        existing = await get_config(db)
        merged = _merge_config_update(
            existing,
            body["config"],
            allow_secret_updates=bool(_user.get("is_admin")),
        )
        await save_config(db, merged)
    if "ideas" in body:
        await replace_ideas(db, body["ideas"])
    if "jokes" in body:
        await replace_jokes(db, body["jokes"])
    if "showSlots" in body:
        await replace_show_slots(db, body["showSlots"])
    if "assignments" in body:
        await replace_assignments(db, body["assignments"])
    return {"ok": True}
