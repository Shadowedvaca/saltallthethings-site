"""Public (unauthenticated) routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from satt.crud import get_homepage_config, get_released_episodes
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
