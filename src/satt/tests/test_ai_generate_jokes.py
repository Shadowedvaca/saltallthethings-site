"""Tests for POST /api/ai/generate-jokes.

Mocks httpx.AsyncClient so no real AI API calls are made.
Verifies used jokes are injected into the system prompt.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from httpx import AsyncClient

from satt.config import get_settings
from satt.database import get_db
from satt.main import app


def _token() -> str:
    settings = get_settings()
    payload = {
        "user_id": 1,
        "username": "testuser",
        "is_admin": True,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def _fake_config(ai_model: str = "claude") -> dict:
    return {
        "aiModel": ai_model,
        "claudeApiKey": "sk-ant-test" if ai_model == "claude" else "",
        "claudeModelId": "claude-sonnet-4-5-20250929",
        "openaiApiKey": "sk-openai-test" if ai_model == "openai" else "",
        "openaiModelId": "gpt-4o",
        "jokeContext": "You are a comedy writer for Salt All The Things.",
        "jokeCount": 3,
    }


_FAKE_JOKES_DB = [
    {"id": "j1", "text": "Why did the WoW player cry?", "status": "used"},
    {"id": "j2", "text": "I asked my healer for help.", "status": "unused"},
    {"id": "j3", "text": "Salt is nature's seasoning.", "status": "used"},
]

_VALID_JOKE_RESPONSE = ["Joke alpha", "Joke beta", "Joke gamma"]


async def _override_get_db():
    yield AsyncMock()


def _mock_httpx_client_claude(jokes: list[str]) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(
        return_value={"content": [{"type": "text", "text": json.dumps(jokes)}]}
    )
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _mock_httpx_client_openai(jokes: list[str]) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(
        return_value={
            "choices": [{"message": {"content": json.dumps(jokes)}}]
        }
    )
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.mark.asyncio
async def test_generate_jokes_claude_success(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db
    mock_client = _mock_httpx_client_claude(_VALID_JOKE_RESPONSE)

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config("claude"))):
        with patch("satt.routes.ai.get_jokes", new=AsyncMock(return_value=[])):
            with patch("satt.ai_client.httpx.AsyncClient", return_value=mock_client):
                resp = await client.post(
                    "/api/ai/generate-jokes",
                    json={"themeHint": ""},
                    headers={"Authorization": f"Bearer {_token()}"},
                )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["jokes"] == _VALID_JOKE_RESPONSE


@pytest.mark.asyncio
async def test_generate_jokes_openai_success(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db
    mock_client = _mock_httpx_client_openai(_VALID_JOKE_RESPONSE)

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config("openai"))):
        with patch("satt.routes.ai.get_jokes", new=AsyncMock(return_value=[])):
            with patch("satt.ai_client.httpx.AsyncClient", return_value=mock_client):
                resp = await client.post(
                    "/api/ai/generate-jokes",
                    json={"themeHint": "housing"},
                    headers={"Authorization": f"Bearer {_token()}"},
                )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["jokes"] == _VALID_JOKE_RESPONSE


@pytest.mark.asyncio
async def test_generate_jokes_used_jokes_in_prompt(client: AsyncClient):
    """Verify that jokes with status='used' are injected into the system prompt."""
    app.dependency_overrides[get_db] = _override_get_db
    captured: list = []

    async def mock_call_ai(system_prompt, user_prompt, config):
        captured.append({"system": system_prompt, "user": user_prompt})
        return json.dumps(_VALID_JOKE_RESPONSE)

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config())):
        with patch("satt.routes.ai.get_jokes", new=AsyncMock(return_value=_FAKE_JOKES_DB)):
            with patch("satt.routes.ai.call_ai", new=mock_call_ai):
                resp = await client.post(
                    "/api/ai/generate-jokes",
                    json={"themeHint": ""},
                    headers={"Authorization": f"Bearer {_token()}"},
                )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert len(captured) == 1

    system_prompt = captured[0]["system"]
    # Only used jokes should appear in the prompt
    assert "Why did the WoW player cry?" in system_prompt
    assert "Salt is nature's seasoning." in system_prompt
    # Unused joke should NOT be in the prompt
    assert "I asked my healer for help." not in system_prompt
    assert "ALREADY USED JOKES" in system_prompt


@pytest.mark.asyncio
async def test_generate_jokes_no_used_jokes_no_section(client: AsyncClient):
    """When there are no used jokes, the 'ALREADY USED JOKES' section is omitted."""
    app.dependency_overrides[get_db] = _override_get_db
    captured: list = []

    async def mock_call_ai(system_prompt, user_prompt, config):
        captured.append(system_prompt)
        return json.dumps(_VALID_JOKE_RESPONSE)

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config())):
        with patch("satt.routes.ai.get_jokes", new=AsyncMock(return_value=[])):
            with patch("satt.routes.ai.call_ai", new=mock_call_ai):
                resp = await client.post(
                    "/api/ai/generate-jokes",
                    json={"themeHint": ""},
                    headers={"Authorization": f"Bearer {_token()}"},
                )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert "ALREADY USED JOKES" not in captured[0]


@pytest.mark.asyncio
async def test_generate_jokes_missing_api_key_returns_400(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db
    config = _fake_config("claude")
    config["claudeApiKey"] = ""
    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=config)):
        with patch("satt.routes.ai.get_jokes", new=AsyncMock(return_value=[])):
            resp = await client.post(
                "/api/ai/generate-jokes",
                json={"themeHint": ""},
                headers={"Authorization": f"Bearer {_token()}"},
            )
    app.dependency_overrides.clear()
    assert resp.status_code == 400
    assert "No API key" in resp.json()["error"]


@pytest.mark.asyncio
async def test_generate_jokes_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/ai/generate-jokes",
        json={"themeHint": ""},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_generate_jokes_theme_hint_in_user_prompt(client: AsyncClient):
    """Verify the theme hint appears in the user prompt."""
    app.dependency_overrides[get_db] = _override_get_db
    captured: list = []

    async def mock_call_ai(system_prompt, user_prompt, config):
        captured.append(user_prompt)
        return json.dumps(_VALID_JOKE_RESPONSE)

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config())):
        with patch("satt.routes.ai.get_jokes", new=AsyncMock(return_value=[])):
            with patch("satt.routes.ai.call_ai", new=mock_call_ai):
                resp = await client.post(
                    "/api/ai/generate-jokes",
                    json={"themeHint": "HOUSING_THEME_MARKER"},
                    headers={"Authorization": f"Bearer {_token()}"},
                )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert "HOUSING_THEME_MARKER" in captured[0]
