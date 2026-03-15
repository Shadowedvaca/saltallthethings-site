"""Post-production queue routes — all require authentication."""

from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from satt.auth import require_auth
from satt.config import get_settings
from satt.crud import (
    get_config,
    get_postproduction_queue,
    get_slots_for_scan,
    set_asset_inventory,
    set_production_file_key,
)
from satt.database import get_db
from satt.gdrive import build_asset_inventory, fetch_file_content, get_drive_access_token

router = APIRouter()


class SetKeyRequest(BaseModel):
    productionFileKey: str


@router.get("/postproduction")
async def get_postproduction(
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list:
    return await get_postproduction_queue(db)


@router.put("/postproduction/{slot_id}/key")
async def put_production_key(
    slot_id: str,
    body: SetKeyRequest,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await set_production_file_key(db, slot_id, body.productionFileKey)
    queue = await get_postproduction_queue(db)
    for row in queue:
        if row["slotId"] == slot_id:
            return row
    raise HTTPException(status_code=404, detail=f"Slot {slot_id!r} not found in post-production queue")


@router.get("/postproduction/{slot_id}/art-direction")
async def get_slot_art_direction(
    slot_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fetch the stored art direction JSON from Drive for a slot."""
    queue = await get_postproduction_queue(db)
    row = next((r for r in queue if r["slotId"] == slot_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Slot not found")

    inv = row.get("assetInventory") or {}
    art_dir = inv.get("art_direction", {})
    file_id = art_dir.get("drive_file_id")
    if not file_id:
        raise HTTPException(status_code=404, detail="No art direction file found for this slot")

    settings = get_settings()
    if not all([
        settings.google_oauth_client_id,
        settings.google_oauth_client_secret,
        settings.google_oauth_refresh_token,
    ]):
        raise HTTPException(status_code=400, detail="Google Drive OAuth not configured")

    try:
        access_token = await get_drive_access_token(
            settings.google_oauth_client_id,
            settings.google_oauth_client_secret,
            settings.google_oauth_refresh_token,
        )
        content = await fetch_file_content(access_token, file_id)
        return json.loads(content)
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch art direction from Drive: {e}")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Art direction file is not valid JSON: {e}")


def _build_scan_config(settings, db_config: dict) -> dict:
    """Merge OAuth credentials from settings into the DB config dict."""
    return {
        **db_config,
        "clientId": settings.google_oauth_client_id,
        "clientSecret": settings.google_oauth_client_secret,
        "refreshToken": settings.google_oauth_refresh_token,
    }


def _check_scan_config(settings, db_config: dict) -> None:
    """Raise 400 if Drive credentials or folder IDs are not fully configured."""
    missing = []
    if not settings.google_oauth_client_id:
        missing.append("GOOGLE_OAUTH_CLIENT_ID")
    if not settings.google_oauth_client_secret:
        missing.append("GOOGLE_OAUTH_CLIENT_SECRET")
    if not settings.google_oauth_refresh_token:
        missing.append("GOOGLE_OAUTH_REFRESH_TOKEN")
    if not db_config.get("gdriveFolderShowRecordings"):
        missing.append("gdriveFolderShowRecordings")
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Drive scan not configured. Missing: {', '.join(missing)}",
        )


@router.post("/postproduction/scan")
async def scan_all_postproduction(
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Scan all eligible slots against Google Drive and update their asset inventories."""
    settings = get_settings()
    db_config = await get_config(db)
    _check_scan_config(settings, db_config)
    scan_config = _build_scan_config(settings, db_config)

    slots = await get_slots_for_scan(db)
    scanned = 0
    errors: list[dict] = []

    for slot in slots:
        try:
            inventory = await build_asset_inventory(
                slot["slot_id"], slot["production_file_key"], scan_config
            )
            await set_asset_inventory(db, slot["slot_id"], inventory)
            scanned += 1
        except Exception as exc:
            errors.append({"slotId": slot["slot_id"], "error": str(exc)})

    return {"scanned": scanned, "errors": errors}


@router.post("/postproduction/{slot_id}/scan")
async def scan_single_postproduction(
    slot_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Scan a single slot's assets and update its inventory."""
    settings = get_settings()
    db_config = await get_config(db)
    _check_scan_config(settings, db_config)
    scan_config = _build_scan_config(settings, db_config)

    slots = await get_slots_for_scan(db)
    slot_data = next((s for s in slots if s["slot_id"] == slot_id), None)
    if slot_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Slot {slot_id!r} not found or not eligible for scanning (needs past record_date and production_file_key).",
        )

    inventory = await build_asset_inventory(
        slot_data["slot_id"], slot_data["production_file_key"], scan_config
    )
    await set_asset_inventory(db, slot_id, inventory)

    queue = await get_postproduction_queue(db)
    for row in queue:
        if row["slotId"] == slot_id:
            return row
    raise HTTPException(status_code=404, detail=f"Slot {slot_id!r} not found in post-production queue")
