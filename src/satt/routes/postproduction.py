"""Post-production queue routes — all require authentication."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from satt.auth import require_auth
from satt.crud import get_postproduction_queue, set_production_file_key
from satt.database import get_db

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
