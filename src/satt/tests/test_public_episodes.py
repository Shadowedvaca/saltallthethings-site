"""Tests for GET /public/episodes — release gating, pagination, PST timezone."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

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


PAST_SLOT = {
    "id": "slot_past",
    "episodeNumber": "EP001",
    "episodeNum": 1,
    "recordDate": "2026-01-01",
    "releaseDate": "2026-01-07",
    "isRollout": False,
    "releaseDateOverride": None,
}

FUTURE_SLOT = {
    "id": "slot_future",
    "episodeNumber": "EP002",
    "episodeNum": 2,
    "recordDate": "2099-01-01",
    "releaseDate": "2099-01-07",
    "isRollout": False,
    "releaseDateOverride": None,
}

IDEA_1 = {
    "id": "idea_ep1",
    "titles": ["Episode One"],
    "selectedTitle": "Episode One",
    "summary": "Summary of ep1.",
    "outline": [],
    "status": "published",
    "imageFileId": None,
    "rawNotes": None,
    "createdAt": "2026-01-01T00:00:00Z",
    "updatedAt": "2026-01-01T00:00:00Z",
}

IDEA_2 = {
    "id": "idea_ep2",
    "titles": ["Episode Two"],
    "selectedTitle": "Episode Two",
    "summary": "Summary of ep2.",
    "outline": [],
    "status": "draft",
    "imageFileId": None,
    "rawNotes": None,
    "createdAt": "2026-01-02T00:00:00Z",
    "updatedAt": "2026-01-02T00:00:00Z",
}


async def _seed_episodes(db_client: AsyncClient):
    await db_client.put("/api/data/ideas", json=[IDEA_1, IDEA_2], headers=_headers())
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT, FUTURE_SLOT], headers=_headers()
    )
    await db_client.put(
        "/api/data/assignments",
        json={"slot_past": "idea_ep1", "slot_future": "idea_ep2"},
        headers=_headers(),
    )


@pytest.mark.asyncio
async def test_public_episodes_returns_200(db_client: AsyncClient):
    await _seed_episodes(db_client)
    response = await db_client.get("/public/episodes")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_public_episodes_only_released(db_client: AsyncClient):
    await _seed_episodes(db_client)
    response = await db_client.get("/public/episodes")
    body = response.json()
    assert "episodes" in body
    episode_numbers = [ep["episodeNumber"] for ep in body["episodes"]]
    assert "EP001" in episode_numbers
    assert "EP002" not in episode_numbers


@pytest.mark.asyncio
async def test_public_episodes_shape(db_client: AsyncClient):
    await _seed_episodes(db_client)
    response = await db_client.get("/public/episodes")
    body = response.json()
    assert "page" in body
    assert "limit" in body
    assert "total" in body
    ep = body["episodes"][0]
    assert "episodeNumber" in ep
    assert "title" in ep
    assert "summary" in ep
    assert "releaseDate" in ep


@pytest.mark.asyncio
async def test_public_episodes_cache_header(db_client: AsyncClient):
    await _seed_episodes(db_client)
    response = await db_client.get("/public/episodes")
    assert "Cache-Control" in response.headers
    assert "max-age=300" in response.headers["Cache-Control"]


@pytest.mark.asyncio
async def test_public_episodes_pagination(db_client: AsyncClient):
    # Add several past episodes
    ideas = []
    slots = []
    assignments = {}
    for i in range(1, 6):
        idea_id = f"pg_idea_{i}"
        slot_id = f"pg_slot_{i}"
        ideas.append({
            "id": idea_id,
            "titles": [f"Episode {i}"],
            "selectedTitle": f"Episode {i}",
            "summary": f"Summary {i}",
            "outline": [],
            "status": "published",
            "imageFileId": None,
            "rawNotes": None,
            "createdAt": f"2026-01-0{i}T00:00:00Z",
            "updatedAt": f"2026-01-0{i}T00:00:00Z",
        })
        slots.append({
            "id": slot_id,
            "episodeNumber": f"EP{i:03d}",
            "episodeNum": i,
            "recordDate": f"2026-01-0{i}",
            "releaseDate": f"2026-01-0{i}",
            "isRollout": False,
            "releaseDateOverride": None,
        })
        assignments[slot_id] = idea_id

    await db_client.put("/api/data/ideas", json=ideas, headers=_headers())
    await db_client.put("/api/data/showSlots", json=slots, headers=_headers())
    await db_client.put("/api/data/assignments", json=assignments, headers=_headers())

    resp_p1 = await db_client.get("/public/episodes?page=1&limit=3")
    assert resp_p1.status_code == 200
    body_p1 = resp_p1.json()
    assert len(body_p1["episodes"]) == 3
    assert body_p1["page"] == 1
    assert body_p1["total"] == 5

    resp_p2 = await db_client.get("/public/episodes?page=2&limit=3")
    assert resp_p2.status_code == 200
    body_p2 = resp_p2.json()
    assert len(body_p2["episodes"]) == 2


@pytest.mark.asyncio
async def test_public_episodes_release_date_override(db_client: AsyncClient):
    """A slot with a past releaseDateOverride should appear even if base date is future."""
    idea = {
        "id": "override_idea",
        "titles": ["Override Episode"],
        "selectedTitle": "Override Episode",
        "summary": "Override summary.",
        "outline": [],
        "status": "published",
        "imageFileId": None,
        "rawNotes": None,
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
    }
    slot = {
        "id": "override_slot",
        "episodeNumber": "EP999",
        "episodeNum": 999,
        "recordDate": "2099-06-01",
        "releaseDate": "2099-06-08",
        "isRollout": False,
        "releaseDateOverride": "2026-01-05",  # past override
    }
    await db_client.put("/api/data/ideas", json=[idea], headers=_headers())
    await db_client.put("/api/data/showSlots", json=[slot], headers=_headers())
    await db_client.put(
        "/api/data/assignments",
        json={"override_slot": "override_idea"},
        headers=_headers(),
    )

    response = await db_client.get("/public/episodes")
    numbers = [ep["episodeNumber"] for ep in response.json()["episodes"]]
    assert "EP999" in numbers
