"""Tests for the /api/health endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient):
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "timestamp" in body


@pytest.mark.asyncio
async def test_health_timestamp_is_iso8601(client: AsyncClient):
    from datetime import datetime

    response = await client.get("/api/health")
    assert response.status_code == 200
    ts = response.json()["timestamp"]
    # Should parse without error
    datetime.fromisoformat(ts)
