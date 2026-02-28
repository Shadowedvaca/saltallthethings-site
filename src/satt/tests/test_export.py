"""Tests for GET /api/export."""

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


@pytest.mark.asyncio
async def test_export_returns_all_five_keys(db_client: AsyncClient):
    response = await db_client.get(
        "/api/export", headers={"Authorization": f"Bearer {_token()}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"config", "ideas", "jokes", "showSlots", "assignments"}


@pytest.mark.asyncio
async def test_export_ideas_is_list(db_client: AsyncClient):
    response = await db_client.get(
        "/api/export", headers={"Authorization": f"Bearer {_token()}"}
    )
    assert isinstance(response.json()["ideas"], list)


@pytest.mark.asyncio
async def test_export_jokes_is_list(db_client: AsyncClient):
    response = await db_client.get(
        "/api/export", headers={"Authorization": f"Bearer {_token()}"}
    )
    assert isinstance(response.json()["jokes"], list)


@pytest.mark.asyncio
async def test_export_show_slots_is_list(db_client: AsyncClient):
    response = await db_client.get(
        "/api/export", headers={"Authorization": f"Bearer {_token()}"}
    )
    assert isinstance(response.json()["showSlots"], list)


@pytest.mark.asyncio
async def test_export_assignments_is_dict(db_client: AsyncClient):
    response = await db_client.get(
        "/api/export", headers={"Authorization": f"Bearer {_token()}"}
    )
    assert isinstance(response.json()["assignments"], dict)


@pytest.mark.asyncio
async def test_export_config_is_dict(db_client: AsyncClient):
    response = await db_client.get(
        "/api/export", headers={"Authorization": f"Bearer {_token()}"}
    )
    assert isinstance(response.json()["config"], dict)
