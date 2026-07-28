"""Health check endpoint."""

from datetime import datetime, timezone

from fastapi import APIRouter

from satt.version import APP_VERSION

router = APIRouter()


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "version": APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
