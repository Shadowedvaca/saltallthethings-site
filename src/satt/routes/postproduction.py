"""Post-production queue routes — all require authentication."""

from __future__ import annotations

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
from satt.gdrive import build_asset_inventory

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
    if not db_config.get("gdriveFolderRawAudio"):
        missing.append("gdriveFolderRawAudio")
    if not db_config.get("gdriveFolderFinishedAudio"):
        missing.append("gdriveFolderFinishedAudio")
    if not db_config.get("gdriveFolderTranscripts"):
        missing.append("gdriveFolderTranscripts")
    if not db_config.get("gdriveFolderCoverArt"):
        missing.append("gdriveFolderCoverArt")
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
