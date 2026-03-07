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


@router.post("/postproduction/scan")
async def scan_all_postproduction(
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Scan all eligible slots against Google Drive and update their asset inventories."""
    settings = get_settings()
    service_account_json = settings.google_service_account_json

    db_config = await get_config(db)
    folder_raw = db_config.get("gdriveFolderRawAudio", "")
    folder_finished = db_config.get("gdriveFolderFinishedAudio", "")
    folder_transcripts = db_config.get("gdriveFolderTranscripts", "")
    folder_art = db_config.get("gdriveFolderCoverArt", "")

    if not all([service_account_json, folder_raw, folder_finished, folder_transcripts, folder_art]):
        raise HTTPException(
            status_code=400,
            detail="Google Drive folder IDs and service account must be configured before scanning.",
        )

    scan_config = {
        **db_config,
        "serviceAccountJson": service_account_json,
    }

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
    service_account_json = settings.google_service_account_json

    db_config = await get_config(db)
    folder_raw = db_config.get("gdriveFolderRawAudio", "")
    folder_finished = db_config.get("gdriveFolderFinishedAudio", "")
    folder_transcripts = db_config.get("gdriveFolderTranscripts", "")
    folder_art = db_config.get("gdriveFolderCoverArt", "")

    if not all([service_account_json, folder_raw, folder_finished, folder_transcripts, folder_art]):
        raise HTTPException(
            status_code=400,
            detail="Google Drive folder IDs and service account must be configured before scanning.",
        )

    slots = await get_slots_for_scan(db)
    slot_data = next((s for s in slots if s["slot_id"] == slot_id), None)
    if slot_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Slot {slot_id!r} not found or not eligible for scanning (needs past record_date and production_file_key).",
        )

    scan_config = {**db_config, "serviceAccountJson": service_account_json}
    inventory = await build_asset_inventory(
        slot_data["slot_id"], slot_data["production_file_key"], scan_config
    )
    await set_asset_inventory(db, slot_id, inventory)

    queue = await get_postproduction_queue(db)
    for row in queue:
        if row["slotId"] == slot_id:
            return row
    raise HTTPException(status_code=404, detail=f"Slot {slot_id!r} not found in post-production queue")
