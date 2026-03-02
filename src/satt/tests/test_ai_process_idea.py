"""Tests for POST /api/ai/process-idea.

Mocks httpx.AsyncClient so no real AI API calls are made.
Uses a real JWT for auth (no DB needed for auth checks).
Mocks crud.get_config via patch so no DB connection is needed.
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


def _token(is_admin: bool = True) -> str:
    settings = get_settings()
    payload = {
        "user_id": 1,
        "username": "testuser",
        "is_admin": is_admin,
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
        "showContext": "Test show context.",
        "segments": [
            {"id": "opening", "name": "Opening Hook / Intro", "description": "Set the tone"},
            {"id": "main", "name": "Main Topic", "description": "Core discussion"},
        ],
        "titleCount": 3,
    }


def _mock_httpx_client(json_body: dict) -> MagicMock:
    """Build a mock httpx.AsyncClient that returns the given JSON body."""
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=json_body)

    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


_VALID_IDEA_RESPONSE = {
    "titles": ["Title One", "Title Two", "Title Three"],
    "summary": "A great episode about WoW.",
    "outline": [
        {
            "segmentId": "opening",
            "segmentName": "Opening Hook / Intro",
            "talkingPoints": ["Point one", "Point two"],
        }
    ],
}


async def _override_get_db():
    yield AsyncMock()


@pytest.mark.asyncio
async def test_process_idea_claude_success(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db
    mock_client = _mock_httpx_client(
        {"content": [{"type": "text", "text": json.dumps(_VALID_IDEA_RESPONSE)}]}
    )

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config("claude"))):
        with patch("satt.ai_client.httpx.AsyncClient", return_value=mock_client):
            resp = await client.post(
                "/api/ai/process-idea",
                json={"rawNotes": "Raw ideas about the housing market in WoW."},
                headers={"Authorization": f"Bearer {_token()}"},
            )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["titles"] == _VALID_IDEA_RESPONSE["titles"]
    assert data["summary"] == _VALID_IDEA_RESPONSE["summary"]
    assert isinstance(data["outline"], list)


@pytest.mark.asyncio
async def test_process_idea_openai_success(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db
    mock_client = _mock_httpx_client(
        {
            "choices": [
                {"message": {"content": json.dumps(_VALID_IDEA_RESPONSE)}}
            ]
        }
    )

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config("openai"))):
        with patch("satt.ai_client.httpx.AsyncClient", return_value=mock_client):
            resp = await client.post(
                "/api/ai/process-idea",
                json={"rawNotes": "Raw ideas about the raid patch."},
                headers={"Authorization": f"Bearer {_token()}"},
            )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["titles"] == _VALID_IDEA_RESPONSE["titles"]


@pytest.mark.asyncio
async def test_process_idea_empty_notes_returns_422(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db
    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config())):
        resp = await client.post(
            "/api/ai/process-idea",
            json={"rawNotes": "   "},
            headers={"Authorization": f"Bearer {_token()}"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_process_idea_missing_api_key_returns_400(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db
    config = _fake_config("claude")
    config["claudeApiKey"] = ""  # no key
    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=config)):
        resp = await client.post(
            "/api/ai/process-idea",
            json={"rawNotes": "Some notes here."},
            headers={"Authorization": f"Bearer {_token()}"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 400
    assert "No API key" in resp.json()["error"]


@pytest.mark.asyncio
async def test_process_idea_upstream_error_returns_500(client: AsyncClient):
    import httpx as _httpx

    app.dependency_overrides[get_db] = _override_get_db

    response = MagicMock()
    response.raise_for_status = MagicMock(
        side_effect=_httpx.HTTPStatusError(
            "500 error", request=MagicMock(), response=MagicMock()
        )
    )
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config())):
        with patch("satt.ai_client.httpx.AsyncClient", return_value=mock_client):
            resp = await client.post(
                "/api/ai/process-idea",
                json={"rawNotes": "Some notes."},
                headers={"Authorization": f"Bearer {_token()}"},
            )
    app.dependency_overrides.clear()
    assert resp.status_code == 500
    assert "AI API error" in resp.json()["error"]


@pytest.mark.asyncio
async def test_process_idea_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/ai/process-idea",
        json={"rawNotes": "Some notes."},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_process_idea_prompt_contains_raw_notes(client: AsyncClient):
    """Verify the rawNotes are forwarded to the AI call."""
    app.dependency_overrides[get_db] = _override_get_db
    captured_calls: list = []

    async def mock_call_ai(system_prompt, user_prompt, config):
        captured_calls.append({"system": system_prompt, "user": user_prompt})
        return json.dumps(_VALID_IDEA_RESPONSE)

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config())):
        with patch("satt.routes.ai.call_ai", new=mock_call_ai):
            resp = await client.post(
                "/api/ai/process-idea",
                json={"rawNotes": "MARKER_TEXT_FOR_TEST"},
                headers={"Authorization": f"Bearer {_token()}"},
            )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert len(captured_calls) == 1
    assert "MARKER_TEXT_FOR_TEST" in captured_calls[0]["user"]
