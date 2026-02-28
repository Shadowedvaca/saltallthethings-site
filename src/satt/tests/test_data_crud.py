"""Tests for GET /api/data/:key and PUT /api/data/:key."""

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


AUTH = property(lambda self: {"Authorization": f"Bearer {_token()}"})


def _headers() -> dict:
    return {"Authorization": f"Bearer {_token()}"}


# ---------------------------------------------------------------------------
# Unknown key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_unknown_key_returns_400(db_client: AsyncClient):
    response = await db_client.get("/api/data/nope", headers=_headers())
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_put_unknown_key_returns_400(db_client: AsyncClient):
    response = await db_client.put("/api/data/nope", json={}, headers=_headers())
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Jokes round-trip
# ---------------------------------------------------------------------------

JOKE = {
    "id": "test_joke_1",
    "text": "Why so salty?",
    "status": "active",
    "source": "manual",
    "usedByIdeaId": None,
    "createdAt": "2026-01-01T00:00:00Z",
}


@pytest.mark.asyncio
async def test_put_jokes_then_get(db_client: AsyncClient):
    put_resp = await db_client.put(
        "/api/data/jokes", json=[JOKE], headers=_headers()
    )
    assert put_resp.status_code == 200
    assert put_resp.json() == {"ok": True}

    get_resp = await db_client.get("/api/data/jokes", headers=_headers())
    assert get_resp.status_code == 200
    jokes = get_resp.json()
    assert len(jokes) == 1
    assert jokes[0]["id"] == JOKE["id"]
    assert jokes[0]["text"] == JOKE["text"]
    assert jokes[0]["status"] == JOKE["status"]
    assert jokes[0]["source"] == JOKE["source"]
    assert jokes[0]["usedByIdeaId"] is None


@pytest.mark.asyncio
async def test_put_jokes_camelcase_keys(db_client: AsyncClient):
    await db_client.put("/api/data/jokes", json=[JOKE], headers=_headers())
    get_resp = await db_client.get("/api/data/jokes", headers=_headers())
    joke = get_resp.json()[0]
    assert "usedByIdeaId" in joke
    assert "createdAt" in joke


@pytest.mark.asyncio
async def test_put_jokes_replaces_all(db_client: AsyncClient):
    joke2 = {**JOKE, "id": "test_joke_2", "text": "Another one"}
    await db_client.put("/api/data/jokes", json=[JOKE, joke2], headers=_headers())
    await db_client.put("/api/data/jokes", json=[joke2], headers=_headers())
    get_resp = await db_client.get("/api/data/jokes", headers=_headers())
    ids = [j["id"] for j in get_resp.json()]
    assert ids == ["test_joke_2"]


# ---------------------------------------------------------------------------
# Ideas round-trip
# ---------------------------------------------------------------------------

IDEA = {
    "id": "test_idea_1",
    "titles": ["Great Episode Title", "Another Title"],
    "selectedTitle": "Great Episode Title",
    "summary": "This episode is about stuff.",
    "outline": [{"segmentId": "opening", "segmentName": "Intro", "talkingPoints": ["Hi"]}],
    "status": "draft",
    "imageFileId": None,
    "rawNotes": None,
    "createdAt": "2026-01-10T00:00:00Z",
    "updatedAt": "2026-01-10T00:00:00Z",
}


@pytest.mark.asyncio
async def test_put_ideas_then_get(db_client: AsyncClient):
    put_resp = await db_client.put(
        "/api/data/ideas", json=[IDEA], headers=_headers()
    )
    assert put_resp.status_code == 200

    get_resp = await db_client.get("/api/data/ideas", headers=_headers())
    assert get_resp.status_code == 200
    ideas = get_resp.json()
    assert len(ideas) == 1
    assert ideas[0]["id"] == IDEA["id"]
    assert ideas[0]["selectedTitle"] == IDEA["selectedTitle"]
    assert ideas[0]["titles"] == IDEA["titles"]
    assert ideas[0]["outline"] == IDEA["outline"]


@pytest.mark.asyncio
async def test_idea_preserves_created_at_on_update(db_client: AsyncClient):
    await db_client.put("/api/data/ideas", json=[IDEA], headers=_headers())
    updated = {**IDEA, "summary": "Updated summary", "updatedAt": "2026-02-01T00:00:00Z"}
    await db_client.put("/api/data/ideas", json=[updated], headers=_headers())
    get_resp = await db_client.get("/api/data/ideas", headers=_headers())
    idea = get_resp.json()[0]
    # createdAt should be preserved from original insert
    assert idea["createdAt"].startswith("2026-01-10")
    assert idea["summary"] == "Updated summary"


# ---------------------------------------------------------------------------
# Show Slots round-trip
# ---------------------------------------------------------------------------

SLOT = {
    "id": "slot_test_1",
    "episodeNumber": "EP099",
    "episodeNum": 99,
    "recordDate": "2026-03-10",
    "releaseDate": "2026-03-17",
    "isRollout": False,
    "releaseDateOverride": None,
}


@pytest.mark.asyncio
async def test_put_show_slots_then_get(db_client: AsyncClient):
    put_resp = await db_client.put(
        "/api/data/showSlots", json=[SLOT], headers=_headers()
    )
    assert put_resp.status_code == 200

    get_resp = await db_client.get("/api/data/showSlots", headers=_headers())
    slots = get_resp.json()
    assert len(slots) == 1
    assert slots[0]["id"] == SLOT["id"]
    assert slots[0]["episodeNumber"] == SLOT["episodeNumber"]
    assert slots[0]["episodeNum"] == SLOT["episodeNum"]
    assert slots[0]["recordDate"] == SLOT["recordDate"]
    assert slots[0]["releaseDate"] == SLOT["releaseDate"]
    assert slots[0]["isRollout"] == SLOT["isRollout"]
    assert slots[0]["releaseDateOverride"] is None


# ---------------------------------------------------------------------------
# Assignments round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_assignments_then_get(db_client: AsyncClient):
    # Need an idea and a slot to satisfy FK constraints
    await db_client.put("/api/data/ideas", json=[IDEA], headers=_headers())
    await db_client.put("/api/data/showSlots", json=[SLOT], headers=_headers())

    assignments = {"slot_test_1": "test_idea_1"}
    put_resp = await db_client.put(
        "/api/data/assignments", json=assignments, headers=_headers()
    )
    assert put_resp.status_code == 200

    get_resp = await db_client.get("/api/data/assignments", headers=_headers())
    assert get_resp.json() == assignments


# ---------------------------------------------------------------------------
# Config round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_config_then_get(db_client: AsyncClient):
    config = {"aiModel": "claude", "youtubeVideo1": "abc123"}
    put_resp = await db_client.put(
        "/api/data/config", json=config, headers=_headers()
    )
    assert put_resp.status_code == 200

    get_resp = await db_client.get("/api/data/config", headers=_headers())
    assert get_resp.json() == config
