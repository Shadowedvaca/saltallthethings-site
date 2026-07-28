"""Health check endpoint."""

from datetime import datetime, timezone

from fastapi import APIRouter

from satt.config import get_settings
from satt.version import APP_VERSION

router = APIRouter()


@router.get("/health")
async def health():
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.environment,
        "version": APP_VERSION,
        "commit": settings.commit_sha,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
