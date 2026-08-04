"""Endpoint tests for authenticated AI-assisted Top 3 concept generation."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import jwt
import pytest
from httpx import AsyncClient

from satt.config import get_settings
from satt.database import get_db
from satt.main import app


def _token() -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "user_id": 1,
            "username": "testuser",
            "is_admin": True,
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def _config(provider: str = "claude") -> dict:
    return {
        "aiModel": provider,
        "claudeApiKey": "configured-test-value" if provider == "claude" else "",
        "claudeModelId": "claude-test-model",
        "openaiApiKey": "configured-test-value" if provider == "openai" else "",
        "openaiModelId": "gpt-test-model",
    }


def _proposal(name: str = "Top Dungeon Snacks") -> str:
    return json.dumps(
        {
            "name": name,
            "description": "Rank three snacks for a dungeon run.",
            "rules": "Explain each rank and use no conjured food.",
            "aiExample": ["Cheese wheel", "Spiced jerky", "Moonberry juice"],
        }
    )


async def _override_get_db():
    yield AsyncMock()


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "model_id"),
    [("claude", "claude-test-model"), ("openai", "gpt-test-model")],
)
async def test_top3_generation_returns_validated_provider_provenance(
    client: AsyncClient, provider: str, model_id: str
):
    app.dependency_overrides[get_db] = _override_get_db
    mock_call = AsyncMock(return_value=_proposal())
    try:
        with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_config(provider))):
            with patch("satt.routes.ai.call_ai", new=mock_call):
                response = await client.post(
                    "/api/ai/top3-concept",
                    json={
                        "name": "Top Dungeon Snacks",
                        "description": "Dungeon snack notes.",
                        "rules": "No conjured food.",
                        "hostNotes": "Private planning context.",
                    },
                    headers=_headers(),
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Top Dungeon Snacks"
    assert body["source"] == "ai"
    assert body["aiProvider"] == provider
    assert body["aiModelId"] == model_id
    assert body["aiGeneratedAt"].endswith("Z")
    assert len(body["aiExample"]) == 3
    assert body["hostNotes"] == "Private planning context."
    assert "picks" not in body and "participant" not in body
    assert mock_call.await_count == 1


@pytest.mark.asyncio
async def test_top3_generation_without_name_accepts_generated_name(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db
    try:
        with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_config())):
            with patch("satt.routes.ai.call_ai", new=AsyncMock(return_value=_proposal("Raid Night Fuel"))):
                response = await client.post(
                    "/api/ai/top3-concept",
                    json={"description": "Rank snacks for raid night."},
                    headers=_headers(),
                )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["name"] == "Raid Night Fuel"


@pytest.mark.asyncio
async def test_top3_generation_is_read_only_for_the_shared_revision(
    db_client: AsyncClient,
):
    before = await db_client.get("/api/top3/concepts", headers=_headers())
    assert before.status_code == 200
    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_config())):
        with patch("satt.routes.ai.call_ai", new=AsyncMock(return_value=_proposal())):
            generated = await db_client.post(
                "/api/ai/top3-concept",
                json={"description": "Rank dungeon snacks."},
                headers=_headers(),
            )
    after = await db_client.get("/api/top3/concepts", headers=_headers())

    assert generated.status_code == 200
    assert after.status_code == 200
    assert after.json()["revision"] == before.json()["revision"]
    assert after.json()["concepts"] == before.json()["concepts"]


@pytest.mark.asyncio
async def test_top3_generation_repairs_once_then_accepts(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db
    mock_call = AsyncMock(
        side_effect=[
            _proposal("Changed Name"),
            _proposal("Top Dungeon Snacks"),
        ]
    )
    try:
        with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_config())):
            with patch("satt.routes.ai.call_ai", new=mock_call):
                response = await client.post(
                    "/api/ai/top3-concept",
                    json={
                        "name": "Top Dungeon Snacks",
                        "description": "Rank dungeon snacks.",
                    },
                    headers=_headers(),
                )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert mock_call.await_count == 2
    assert "preserve the supplied name" in mock_call.await_args_list[1].args[1]


@pytest.mark.asyncio
async def test_top3_generation_rejects_after_exactly_one_failed_repair(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db
    mock_call = AsyncMock(return_value="not-json")
    try:
        with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_config())):
            with patch("satt.routes.ai.call_ai", new=mock_call):
                response = await client.post(
                    "/api/ai/top3-concept",
                    json={"description": "Rank dungeon snacks."},
                    headers=_headers(),
                )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 502
    assert mock_call.await_count == 2
    assert "after one repair attempt" in response.json()["error"]


@pytest.mark.asyncio
async def test_top3_generation_missing_credential_is_actionable_and_secret_safe(
    client: AsyncClient,
):
    app.dependency_overrides[get_db] = _override_get_db
    config = _config()
    config["claudeApiKey"] = ""
    mock_call = AsyncMock()
    try:
        with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=config)):
            with patch("satt.routes.ai.call_ai", new=mock_call):
                response = await client.post(
                    "/api/ai/top3-concept",
                    json={"description": "Rank dungeon snacks."},
                    headers=_headers(),
                )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 400
    assert response.json() == {"error": "No API key configured for claude"}
    mock_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_top3_generation_provider_error_does_not_echo_exception(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db
    request = httpx.Request("POST", "https://provider.invalid")
    provider_error = httpx.RequestError("credential-looking-private-value", request=request)
    try:
        with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_config())):
            with patch("satt.routes.ai.call_ai", new=AsyncMock(side_effect=provider_error)):
                response = await client.post(
                    "/api/ai/top3-concept",
                    json={"description": "Rank dungeon snacks."},
                    headers=_headers(),
                )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 502
    assert "retry or verify" in response.json()["error"]
    assert "credential-looking-private-value" not in response.text


@pytest.mark.asyncio
async def test_top3_generation_requires_auth_and_rejects_extra_fields(client: AsyncClient):
    unauthenticated = await client.post(
        "/api/ai/top3-concept", json={"description": "Rank snacks."}
    )
    assert unauthenticated.status_code == 401
    extra = await client.post(
        "/api/ai/top3-concept",
        json={"description": "Rank snacks.", "participantPicks": ["A", "B", "C"]},
        headers=_headers(),
    )
    assert extra.status_code == 422
