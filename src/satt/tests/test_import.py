"""Tests for PUT /api/import (bulk write)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient

from satt.config import get_settings


def _token() -> str:
    settings = get_settings()
    payload = {
        "user_id": 1,
        "username": "testuser",
        "is_admin": False,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def _headers() -> dict:
    return {"Authorization": f"Bearer {_token()}"}


IMPORT_PAYLOAD = {
    "config": {"aiModel": "claude", "youtubeVideo1": "vid1"},
    "ideas": [
        {
            "id": "import_idea_1",
            "titles": ["Import Title"],
            "selectedTitle": "Import Title",
            "summary": "Imported.",
            "outline": [],
            "status": "draft",
            "imageFileId": None,
            "rawNotes": None,
            "createdAt": "2026-01-15T00:00:00Z",
            "updatedAt": "2026-01-15T00:00:00Z",
        }
    ],
    "jokes": [
        {
            "id": "import_joke_1",
            "text": "Imported joke",
            "status": "active",
            "source": "manual",
            "usedByIdeaId": None,
            "createdAt": "2026-01-15T00:00:00Z",
        }
    ],
    "showSlots": [
        {
            "id": "import_slot_1",
            "episodeNumber": "EP200",
            "episodeNum": 200,
            "recordDate": "2026-04-01",
            "releaseDate": "2026-04-08",
            "isRollout": False,
            "releaseDateOverride": None,
        }
    ],
    "assignments": {"import_slot_1": "import_idea_1"},
}


@pytest.mark.asyncio
async def test_import_returns_ok(db_client: AsyncClient):
    response = await db_client.put(
        "/api/import", json=IMPORT_PAYLOAD, headers=_headers()
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_import_round_trip(db_client: AsyncClient):
    await db_client.put("/api/import", json=IMPORT_PAYLOAD, headers=_headers())

    export = await db_client.get("/api/export", headers=_headers())
    body = export.json()

    assert body["config"]["aiModel"] == "claude"
    assert len(body["ideas"]) == 1
    assert body["ideas"][0]["id"] == "import_idea_1"
    assert len(body["jokes"]) == 1
    assert body["jokes"][0]["id"] == "import_joke_1"
    assert len(body["showSlots"]) == 1
    assert body["showSlots"][0]["id"] == "import_slot_1"
    assert body["assignments"] == {"import_slot_1": "import_idea_1"}


@pytest.mark.asyncio
async def test_import_returns_401_without_auth(client: AsyncClient):
    response = await client.put("/api/import", json=IMPORT_PAYLOAD)
    assert response.status_code == 401
