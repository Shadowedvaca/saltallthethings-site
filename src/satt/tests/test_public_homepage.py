"""Tests for GET /public/homepage."""

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


@pytest.mark.asyncio
async def test_public_homepage_returns_200(db_client: AsyncClient):
    response = await db_client.get("/public/homepage")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_public_homepage_shape(db_client: AsyncClient):
    response = await db_client.get("/public/homepage")
    body = response.json()
    assert "youtubeVideo1" in body
    assert "youtubeVideo2" in body
    assert "youtubeVideo3" in body


@pytest.mark.asyncio
async def test_public_homepage_returns_video_ids_from_config(db_client: AsyncClient):
    config = {
        "youtubeVideo1": "vid111",
        "youtubeVideo2": "vid222",
        "youtubeVideo3": "vid333",
    }
    await db_client.put("/api/data/config", json=config, headers=_headers())

    response = await db_client.get("/public/homepage")
    body = response.json()
    assert body["youtubeVideo1"] == "vid111"
    assert body["youtubeVideo2"] == "vid222"
    assert body["youtubeVideo3"] == "vid333"


@pytest.mark.asyncio
async def test_public_homepage_cache_header(db_client: AsyncClient):
    response = await db_client.get("/public/homepage")
    assert "Cache-Control" in response.headers
    assert "max-age=300" in response.headers["Cache-Control"]


@pytest.mark.asyncio
async def test_public_homepage_no_auth_header_in_db_tests(db_client: AsyncClient):
    """Public endpoint accepts requests with no auth header."""
    response = await db_client.get("/public/homepage")
    assert response.status_code == 200
