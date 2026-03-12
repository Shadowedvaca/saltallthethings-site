"""Public (unauthenticated) routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from satt.config import get_settings
from satt.crud import get_assignments, get_config, get_homepage_config, get_ideas, get_jokes, get_released_episodes, get_show_slots
from satt.database import get_db

router = APIRouter()

_CACHE_5MIN = "public, max-age=300"


@router.get("/episodes")
async def public_episodes(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    data = await get_released_episodes(db, page=page, limit=limit)
    return JSONResponse(content=data, headers={"Cache-Control": _CACHE_5MIN})


@router.get("/homepage")
async def public_homepage(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    data = await get_homepage_config(db)
    return JSONResponse(content=data, headers={"Cache-Control": _CACHE_5MIN})


@router.get("/sv-export")
async def sv_export(
    key: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Server-to-server export for sv-tools. Protected by static API key."""
    settings = get_settings()
    if not settings.sv_export_key or key != settings.sv_export_key:
        raise HTTPException(status_code=403, detail="Forbidden")
    config, ideas, jokes, show_slots, assignments = (
        await get_config(db),
        await get_ideas(db),
        await get_jokes(db),
        await get_show_slots(db),
        await get_assignments(db),
    )
    return JSONResponse(content={
        "config": config,
        "ideas": ideas,
        "jokes": jokes,
        "showSlots": show_slots,
        "assignments": assignments,
    })
