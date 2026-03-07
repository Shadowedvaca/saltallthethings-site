"""Tests for POST /api/ai/generate-art-direction.

Mocks httpx.AsyncClient so no real AI API calls are made.
Verifies art direction shape, artLog update, continuity prompt injection,
transcript validation, and auth guard.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

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
        "artStyleBible": {
            "format": "square 1024x1024",
            "artStyle": "World of Warcraft inspired fantasy digital painting",
            "characters": {
                "bigElemental": "large salt elemental",
                "babyElementals": "small chibi elementals",
            },
            "lighting": "dark moody background",
            "palette": ["icy blue", "navy"],
            "rules": ["no text", "no real people"],
        },
        "artArchetypes": [
            {
                "id": "tavern_talk",
                "name": "Tavern Talk",
                "useFor": ["general discussion"],
                "scene": "tavern scene with microphone",
            },
        ],
        "artLog": [],
    }


class _FakeIdea:
    id = "idea-1"
    selected_title = "War Within Seasons Ranked"
    summary = "An episode about ranked PvP seasons in War Within."
    outline = [{"segmentId": "opening", "talkingPoints": ["What changed in ranked?"]}]


class _FakeSlot:
    episode_number = "EP042"
    episode_num = 42


_VALID_ART_DIRECTION = {
    "topics": ["ranked seasons", "pvp", "patch changes"],
    "tone": "excited and opinionated",
    "archetype": {
        "id": "tavern_talk",
        "name": "Tavern Talk",
        "reason": "General discussion episode about game systems",
    },
    "environment": "cozy tavern with microphone on the table",
    "bigElementalRole": "host behind the bar, gesturing dramatically",
    "babyGags": [
        "one baby spilling salt onto the table",
        "one baby arguing with a tiny ranking board",
    ],
    "props": ["bronze microphone", "salt shaker", "ranking scroll"],
    "sceneSummary": (
        "Tavern talk scene: the big salt elemental hosts a heated discussion about "
        "ranked seasons while baby elementals cause chaos around the bar"
    ),
    "finalImagePrompt": (
        "Square 1024x1024 fantasy digital painting in World of Warcraft style. "
        "Scene: cozy tavern with the big salt elemental as host. No text in image."
    ),
}


async def _override_get_db():
    yield AsyncMock()


@pytest.mark.asyncio
async def test_generate_art_direction_success(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config())):
        with patch("satt.routes.ai.save_config", new=AsyncMock()):
            with patch(
                "satt.routes.ai.get_idea_and_slot",
                new=AsyncMock(return_value=(_FakeIdea(), _FakeSlot())),
            ):
                with patch(
                    "satt.routes.ai.call_ai",
                    new=AsyncMock(return_value=json.dumps(_VALID_ART_DIRECTION)),
                ):
                    resp = await client.post(
                        "/api/ai/generate-art-direction",
                        json={"ideaId": "idea-1", "transcriptText": "This is the full transcript."},
                        headers={"Authorization": f"Bearer {_token()}"},
                    )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["archetype"]["id"] == "tavern_talk"
    assert data["archetype"]["name"] == "Tavern Talk"
    assert "finalImagePrompt" in data
    assert "sceneSummary" in data
    assert isinstance(data["babyGags"], list)
    assert isinstance(data["topics"], list)
    assert "environment" in data
    assert "bigElementalRole" in data
    assert "props" in data
    assert "tone" in data


@pytest.mark.asyncio
async def test_generate_art_direction_artlog_updated(client: AsyncClient):
    """artLog should be appended with the new entry and saved after a successful call."""
    app.dependency_overrides[get_db] = _override_get_db
    saved_configs: list[dict] = []

    async def capture_save(db, config):
        saved_configs.append(json.loads(json.dumps(config)))  # deep copy

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config())):
        with patch("satt.routes.ai.save_config", new=capture_save):
            with patch(
                "satt.routes.ai.get_idea_and_slot",
                new=AsyncMock(return_value=(_FakeIdea(), _FakeSlot())),
            ):
                with patch(
                    "satt.routes.ai.call_ai",
                    new=AsyncMock(return_value=json.dumps(_VALID_ART_DIRECTION)),
                ):
                    resp = await client.post(
                        "/api/ai/generate-art-direction",
                        json={"ideaId": "idea-1", "transcriptText": "Transcript text here."},
                        headers={"Authorization": f"Bearer {_token()}"},
                    )

    app.dependency_overrides.clear()
    assert resp.status_code == 200

    # The last save_config call should include the new artLog entry
    artlog_saves = [c for c in saved_configs if c.get("artLog")]
    assert artlog_saves, "save_config should have been called with a non-empty artLog"
    last_log = artlog_saves[-1]["artLog"]
    assert len(last_log) == 1
    assert last_log[0]["episodeNumber"] == "EP042"
    assert last_log[0]["archetypeId"] == "tavern_talk"
    assert "generatedAt" in last_log[0]


@pytest.mark.asyncio
async def test_generate_art_direction_artlog_capped_at_50(client: AsyncClient):
    """artLog should be capped at 50 entries."""
    app.dependency_overrides[get_db] = _override_get_db

    config = _fake_config()
    config["artLog"] = [
        {"episodeNum": i, "episodeNumber": f"EP{i:03d}", "archetypeId": "tavern_talk",
         "environment": f"env{i}", "babyGags": [], "props": [], "generatedAt": "2026-01-01T00:00:00Z"}
        for i in range(50)
    ]

    saved_configs: list[dict] = []

    async def capture_save(db, cfg):
        saved_configs.append(json.loads(json.dumps(cfg)))

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=config)):
        with patch("satt.routes.ai.save_config", new=capture_save):
            with patch(
                "satt.routes.ai.get_idea_and_slot",
                new=AsyncMock(return_value=(_FakeIdea(), _FakeSlot())),
            ):
                with patch(
                    "satt.routes.ai.call_ai",
                    new=AsyncMock(return_value=json.dumps(_VALID_ART_DIRECTION)),
                ):
                    resp = await client.post(
                        "/api/ai/generate-art-direction",
                        json={"ideaId": "idea-1", "transcriptText": "Long transcript."},
                        headers={"Authorization": f"Bearer {_token()}"},
                    )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    artlog_saves = [c for c in saved_configs if c.get("artLog")]
    assert artlog_saves
    assert len(artlog_saves[-1]["artLog"]) == 50  # capped, not 51


@pytest.mark.asyncio
async def test_generate_art_direction_empty_transcript_returns_422(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config())):
        with patch("satt.routes.ai.save_config", new=AsyncMock()):
            resp = await client.post(
                "/api/ai/generate-art-direction",
                json={"ideaId": "idea-1", "transcriptText": ""},
                headers={"Authorization": f"Bearer {_token()}"},
            )

    app.dependency_overrides.clear()
    assert resp.status_code == 422
    assert "transcriptText" in resp.json()["error"]


@pytest.mark.asyncio
async def test_generate_art_direction_whitespace_transcript_returns_422(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config())):
        with patch("satt.routes.ai.save_config", new=AsyncMock()):
            resp = await client.post(
                "/api/ai/generate-art-direction",
                json={"ideaId": "idea-1", "transcriptText": "   "},
                headers={"Authorization": f"Bearer {_token()}"},
            )

    app.dependency_overrides.clear()
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_generate_art_direction_missing_api_key_returns_400(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db
    config = _fake_config("claude")
    config["claudeApiKey"] = ""

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=config)):
        with patch("satt.routes.ai.save_config", new=AsyncMock()):
            resp = await client.post(
                "/api/ai/generate-art-direction",
                json={"ideaId": "idea-1", "transcriptText": "Transcript text here."},
                headers={"Authorization": f"Bearer {_token()}"},
            )

    app.dependency_overrides.clear()
    assert resp.status_code == 400
    assert "No API key" in resp.json()["error"]


@pytest.mark.asyncio
async def test_generate_art_direction_missing_openai_key_returns_400(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db
    config = _fake_config("openai")
    config["openaiApiKey"] = ""

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=config)):
        with patch("satt.routes.ai.save_config", new=AsyncMock()):
            resp = await client.post(
                "/api/ai/generate-art-direction",
                json={"ideaId": "idea-1", "transcriptText": "Transcript text here."},
                headers={"Authorization": f"Bearer {_token()}"},
            )

    app.dependency_overrides.clear()
    assert resp.status_code == 400
    assert "No API key" in resp.json()["error"]


@pytest.mark.asyncio
async def test_generate_art_direction_continuity_in_prompt_when_artlog_present(
    client: AsyncClient,
):
    """When artLog has entries, continuity rules and log entries appear in the system prompt."""
    app.dependency_overrides[get_db] = _override_get_db
    captured: list[dict] = []

    async def mock_call_ai(system_prompt, user_prompt, config):
        captured.append({"system": system_prompt, "user": user_prompt})
        return json.dumps(_VALID_ART_DIRECTION)

    config = _fake_config()
    config["artLog"] = [
        {
            "episodeNum": 41,
            "episodeNumber": "EP041",
            "archetypeId": "raid_chaos",
            "environment": "battle arena with lava",
            "babyGags": ["one baby spilling salt everywhere"],
            "props": ["microphone", "salt shaker"],
            "generatedAt": "2026-03-01T00:00:00Z",
        }
    ]

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=config)):
        with patch("satt.routes.ai.save_config", new=AsyncMock()):
            with patch(
                "satt.routes.ai.get_idea_and_slot",
                new=AsyncMock(return_value=(_FakeIdea(), _FakeSlot())),
            ):
                with patch("satt.routes.ai.call_ai", new=mock_call_ai):
                    resp = await client.post(
                        "/api/ai/generate-art-direction",
                        json={"ideaId": "idea-1", "transcriptText": "Transcript here."},
                        headers={"Authorization": f"Bearer {_token()}"},
                    )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert len(captured) == 1
    system_prompt = captured[0]["system"]
    assert "CONTINUITY RULES" in system_prompt
    assert "RECENT EPISODE ART LOG" in system_prompt
    assert "EP041" in system_prompt
    assert "raid_chaos" in system_prompt


@pytest.mark.asyncio
async def test_generate_art_direction_no_continuity_when_artlog_empty(client: AsyncClient):
    """When artLog is empty, continuity section should not appear in the prompt."""
    app.dependency_overrides[get_db] = _override_get_db
    captured: list[dict] = []

    async def mock_call_ai(system_prompt, user_prompt, config):
        captured.append({"system": system_prompt})
        return json.dumps(_VALID_ART_DIRECTION)

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config())):
        with patch("satt.routes.ai.save_config", new=AsyncMock()):
            with patch(
                "satt.routes.ai.get_idea_and_slot",
                new=AsyncMock(return_value=(_FakeIdea(), _FakeSlot())),
            ):
                with patch("satt.routes.ai.call_ai", new=mock_call_ai):
                    resp = await client.post(
                        "/api/ai/generate-art-direction",
                        json={"ideaId": "idea-1", "transcriptText": "Transcript here."},
                        headers={"Authorization": f"Bearer {_token()}"},
                    )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert "CONTINUITY RULES" not in captured[0]["system"]
    assert "RECENT EPISODE ART LOG" not in captured[0]["system"]


@pytest.mark.asyncio
async def test_generate_art_direction_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/ai/generate-art-direction",
        json={"ideaId": "idea-1", "transcriptText": "Something here."},
    )
    assert resp.status_code == 401
