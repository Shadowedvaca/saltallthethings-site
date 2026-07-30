"""Tests for the /api/health endpoint."""

import pytest
from httpx import AsyncClient

from satt.config import get_settings
from satt.version import APP_VERSION


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient):
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == get_settings().environment
    assert body["version"] == APP_VERSION
    assert body["commit"] == get_settings().commit_sha
    assert "timestamp" in body

    assert set(body) == {"status", "environment", "version", "commit", "timestamp"}


@pytest.mark.asyncio
async def test_health_timestamp_is_iso8601(client: AsyncClient):
    from datetime import datetime

    response = await client.get("/api/health")
    assert response.status_code == 200
    ts = response.json()["timestamp"]
    # Should parse without error
    datetime.fromisoformat(ts)
