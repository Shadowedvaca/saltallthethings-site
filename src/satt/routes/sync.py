"""Authenticated server-sent canonical-revision notifications."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from satt.auth import require_auth
from satt.crud import get_data_revision
from satt.database import get_session_factory
from satt.models import User

router = APIRouter()
logger = logging.getLogger(__name__)

CANONICAL_RESOURCE = "canonical-state"
ELIGIBLE_RESOURCES = frozenset({CANONICAL_RESOURCE})
POLL_INTERVAL_SECONDS = 1.0
HEARTBEAT_INTERVAL_SECONDS = 15.0


def get_sync_session_factory():
    """Dependency seam for short-lived subscription authorization reads."""
    return get_session_factory()


def _token_is_expired(user: dict, *, now: datetime | None = None) -> bool:
    expires = user.get("exp")
    if isinstance(expires, datetime):
        expiry = expires
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return expiry <= (now or datetime.now(timezone.utc))
    try:
        return float(expires) <= (now or datetime.now(timezone.utc)).timestamp()
    except (TypeError, ValueError):
        return True


async def _read_authorized_revision(factory: Any, user_id: int) -> int | None:
    """Read active-account state and the committed revision in a fresh session."""
    async with factory() as db:
        active = await db.scalar(select(User.is_active).where(User.id == user_id))
        if active is not True:
            return None
        return await get_data_revision(db)


def _revision_event(resource: str, revision: int) -> str:
    payload = json.dumps(
        {"resource": resource, "revision": revision},
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"id: {resource}:{revision}\nevent: revision\ndata: {payload}\n\n"


async def revision_event_stream(
    request: Request,
    *,
    resource: str,
    after: int,
    user: dict,
    factory: Any,
    poll_interval: float = POLL_INTERVAL_SECONDS,
    heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
) -> AsyncIterator[str]:
    """Yield committed revision advances until disconnect or authorization ends."""
    last_revision = after
    next_heartbeat = time.monotonic() + heartbeat_interval
    close_reason = "cancelled"
    try:
        while True:
            if await request.is_disconnected():
                close_reason = "client-disconnected"
                return
            if _token_is_expired(user):
                close_reason = "token-expired"
                return
            revision = await _read_authorized_revision(factory, int(user["user_id"]))
            if revision is None:
                close_reason = "account-inactive"
                return
            if revision > last_revision:
                last_revision = revision
                yield _revision_event(resource, revision)
                next_heartbeat = time.monotonic() + heartbeat_interval
            elif time.monotonic() >= next_heartbeat:
                yield ": keep-alive\n\n"
                next_heartbeat = time.monotonic() + heartbeat_interval
            await asyncio.sleep(poll_interval)
    finally:
        logger.info(
            "revision_stream_closed resource=%s reason=%s",
            resource,
            close_reason,
        )


@router.get("/sync/revisions")
async def subscribe_to_revisions(
    request: Request,
    resource: str = Query(..., min_length=1, max_length=40),
    after: int = Query(default=0, ge=0),
    user: dict = Depends(require_auth),
    factory: Any = Depends(get_sync_session_factory),
) -> StreamingResponse:
    """Subscribe to minimal committed-revision signals for an eligible resource."""
    if resource not in ELIGIBLE_RESOURCES:
        raise HTTPException(status_code=404, detail="Revision resource not found")
    if _token_is_expired(user):
        raise HTTPException(status_code=401, detail="Token expired")
    current = await _read_authorized_revision(factory, int(user["user_id"]))
    if current is None:
        raise HTTPException(status_code=401, detail="Account is not active")

    logger.info("revision_stream_opened resource=%s", resource)

    return StreamingResponse(
        revision_event_stream(
            request,
            resource=resource,
            after=after,
            user=user,
            factory=factory,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
        },
    )
