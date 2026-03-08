"""Tests for POST /api/ai/generate-episode-art.

All httpx, DALL-E, and Drive calls are mocked — no real network calls.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {_token()}"}


def _fake_config() -> dict:
    return {
        "openaiApiKey": "sk-openai-test",
        "gdriveFolderCoverArt": "folder-cover-art-id",
        "gdriveFolderRawAudio": "folder-raw-id",
        "gdriveFolderFinishedAudio": "folder-finished-id",
        "gdriveFolderTranscripts": "folder-transcripts-id",
    }


class _FakeIdea:
    id = "idea-1"
    selected_title = "War Within Seasons Ranked"
    summary = "PvP ranked seasons discussion."
    outline = []


class _FakeSlot:
    id = "slot-1"
    episode_number = "EP042"
    episode_num = 42
    production_file_key = "EP042_War-Within-Seasons-Ranked_2026-03-06"
    asset_inventory = {
        "album_art": {"present": False},
        "raw_audio": {"present": True},
    }


class _FakeSlotWithExistingArt:
    id = "slot-1"
    episode_number = "EP042"
    episode_num = 42
    production_file_key = "EP042_War-Within-Seasons-Ranked_2026-03-06"
    asset_inventory = {
        "album_art": {"present": True, "drive_file_id": "old-art-file-id"},
    }


class _FakeSlotNoKey:
    id = "slot-2"
    episode_number = "EP043"
    episode_num = 43
    production_file_key = None
    asset_inventory = {}


_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # fake PNG bytes
_NEW_FILE_ID = "new-drive-file-id-abc123"
_FAKE_INVENTORY = {"scanned_at": "2026-03-07T00:00:00+00:00", "album_art": {"present": True}}


async def _override_get_db():
    yield AsyncMock()


def _fake_settings():
    s = MagicMock()
    s.google_oauth_client_id = "fake-client-id"
    s.google_oauth_client_secret = "fake-client-secret"
    s.google_oauth_refresh_token = "fake-refresh-token"
    return s


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_episode_art_success(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config())):
        with patch("satt.routes.ai.get_idea_and_slot", new=AsyncMock(return_value=(_FakeIdea(), _FakeSlot()))):
            with patch("satt.routes.ai.call_dalle", new=AsyncMock(return_value=_FAKE_PNG)):
                with patch("satt.routes.ai.get_settings", return_value=_fake_settings()):
                    with patch("satt.routes.ai.get_drive_access_token", new=AsyncMock(return_value="fake-token")):
                        with patch("satt.routes.ai.delete_file", new=AsyncMock()):
                            with patch("satt.routes.ai.upload_file_to_folder", new=AsyncMock(return_value=_NEW_FILE_ID)):
                                with patch("satt.routes.ai.set_idea_image_file_id", new=AsyncMock()):
                                    with patch("satt.routes.ai.build_asset_inventory", new=AsyncMock(return_value=_FAKE_INVENTORY)):
                                        with patch("satt.routes.ai.set_asset_inventory", new=AsyncMock()):
                                            resp = await client.post(
                                                "/api/ai/generate-episode-art",
                                                json={"ideaId": "idea-1", "imagePrompt": "A salt elemental in a tavern."},
                                                headers=_auth_headers(),
                                            )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["imageFileId"] == _NEW_FILE_ID
    assert data["filename"] == "EP042_War-Within-Seasons-Ranked_2026-03-06.png"


@pytest.mark.asyncio
async def test_generate_episode_art_saves_image_file_id(client: AsyncClient):
    """image_file_id should be saved to the idea after successful generation."""
    app.dependency_overrides[get_db] = _override_get_db
    saved_idea_ids: list = []
    saved_file_ids: list = []

    async def capture_save(db, idea_id, file_id):
        saved_idea_ids.append(idea_id)
        saved_file_ids.append(file_id)

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config())):
        with patch("satt.routes.ai.get_idea_and_slot", new=AsyncMock(return_value=(_FakeIdea(), _FakeSlot()))):
            with patch("satt.routes.ai.call_dalle", new=AsyncMock(return_value=_FAKE_PNG)):
                with patch("satt.routes.ai.get_settings", return_value=_fake_settings()):
                    with patch("satt.routes.ai.get_drive_access_token", new=AsyncMock(return_value="fake-token")):
                        with patch("satt.routes.ai.delete_file", new=AsyncMock()):
                            with patch("satt.routes.ai.upload_file_to_folder", new=AsyncMock(return_value=_NEW_FILE_ID)):
                                with patch("satt.routes.ai.set_idea_image_file_id", new=capture_save):
                                    with patch("satt.routes.ai.build_asset_inventory", new=AsyncMock(return_value=_FAKE_INVENTORY)):
                                        with patch("satt.routes.ai.set_asset_inventory", new=AsyncMock()):
                                            resp = await client.post(
                                                "/api/ai/generate-episode-art",
                                                json={"ideaId": "idea-1", "imagePrompt": "Salt elemental scene."},
                                                headers=_auth_headers(),
                                            )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert saved_idea_ids == ["idea-1"]
    assert saved_file_ids == [_NEW_FILE_ID]


@pytest.mark.asyncio
async def test_generate_episode_art_deletes_old_file_on_regeneration(client: AsyncClient):
    """When album_art.drive_file_id exists in asset_inventory, it should be deleted first."""
    app.dependency_overrides[get_db] = _override_get_db
    deleted_ids: list = []

    async def capture_delete(token, file_id):
        deleted_ids.append(file_id)

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config())):
        with patch("satt.routes.ai.get_idea_and_slot", new=AsyncMock(return_value=(_FakeIdea(), _FakeSlotWithExistingArt()))):
            with patch("satt.routes.ai.call_dalle", new=AsyncMock(return_value=_FAKE_PNG)):
                with patch("satt.routes.ai.get_settings", return_value=_fake_settings()):
                    with patch("satt.routes.ai.get_drive_access_token", new=AsyncMock(return_value="fake-token")):
                        with patch("satt.routes.ai.delete_file", new=capture_delete):
                            with patch("satt.routes.ai.upload_file_to_folder", new=AsyncMock(return_value=_NEW_FILE_ID)):
                                with patch("satt.routes.ai.set_idea_image_file_id", new=AsyncMock()):
                                    with patch("satt.routes.ai.build_asset_inventory", new=AsyncMock(return_value=_FAKE_INVENTORY)):
                                        with patch("satt.routes.ai.set_asset_inventory", new=AsyncMock()):
                                            resp = await client.post(
                                                "/api/ai/generate-episode-art",
                                                json={"ideaId": "idea-1", "imagePrompt": "Regenerated scene."},
                                                headers=_auth_headers(),
                                            )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert "old-art-file-id" in deleted_ids


@pytest.mark.asyncio
async def test_generate_episode_art_asset_inventory_updated(client: AsyncClient):
    """asset_inventory should be refreshed via build_asset_inventory after upload."""
    app.dependency_overrides[get_db] = _override_get_db
    inventory_calls: list = []

    async def capture_set_inventory(db, slot_id, inventory):
        inventory_calls.append({"slotId": slot_id, "inventory": inventory})

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config())):
        with patch("satt.routes.ai.get_idea_and_slot", new=AsyncMock(return_value=(_FakeIdea(), _FakeSlot()))):
            with patch("satt.routes.ai.call_dalle", new=AsyncMock(return_value=_FAKE_PNG)):
                with patch("satt.routes.ai.get_settings", return_value=_fake_settings()):
                    with patch("satt.routes.ai.get_drive_access_token", new=AsyncMock(return_value="fake-token")):
                        with patch("satt.routes.ai.delete_file", new=AsyncMock()):
                            with patch("satt.routes.ai.upload_file_to_folder", new=AsyncMock(return_value=_NEW_FILE_ID)):
                                with patch("satt.routes.ai.set_idea_image_file_id", new=AsyncMock()):
                                    with patch("satt.routes.ai.build_asset_inventory", new=AsyncMock(return_value=_FAKE_INVENTORY)):
                                        with patch("satt.routes.ai.set_asset_inventory", new=capture_set_inventory):
                                            resp = await client.post(
                                                "/api/ai/generate-episode-art",
                                                json={"ideaId": "idea-1", "imagePrompt": "Scene."},
                                                headers=_auth_headers(),
                                            )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert len(inventory_calls) == 1
    assert inventory_calls[0]["slotId"] == "slot-1"


# ---------------------------------------------------------------------------
# Guard conditions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_episode_art_no_openai_key_returns_400(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db
    config = _fake_config()
    config["openaiApiKey"] = ""

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=config)):
        resp = await client.post(
            "/api/ai/generate-episode-art",
            json={"ideaId": "idea-1", "imagePrompt": "Scene."},
            headers=_auth_headers(),
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 400
    assert "OpenAI" in resp.json()["error"]


@pytest.mark.asyncio
async def test_generate_episode_art_no_production_key_returns_400(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config())):
        with patch("satt.routes.ai.get_idea_and_slot", new=AsyncMock(return_value=(_FakeIdea(), _FakeSlotNoKey()))):
            resp = await client.post(
                "/api/ai/generate-episode-art",
                json={"ideaId": "idea-1", "imagePrompt": "Scene."},
                headers=_auth_headers(),
            )

    app.dependency_overrides.clear()
    assert resp.status_code == 400
    assert "production file key" in resp.json()["error"].lower()


@pytest.mark.asyncio
async def test_generate_episode_art_content_policy_returns_400(client: AsyncClient):
    """DALL-E 400 (content policy) should surface as a specific 400 with clear message."""
    app.dependency_overrides[get_db] = _override_get_db

    policy_response = MagicMock()
    policy_response.status_code = 400
    policy_error = httpx.HTTPStatusError("content policy", request=MagicMock(), response=policy_response)

    with patch("satt.routes.ai.get_config", new=AsyncMock(return_value=_fake_config())):
        with patch("satt.routes.ai.get_idea_and_slot", new=AsyncMock(return_value=(_FakeIdea(), _FakeSlot()))):
            with patch("satt.routes.ai.call_dalle", new=AsyncMock(side_effect=policy_error)):
                resp = await client.post(
                    "/api/ai/generate-episode-art",
                    json={"ideaId": "idea-1", "imagePrompt": "Offensive prompt."},
                    headers=_auth_headers(),
                )

    app.dependency_overrides.clear()
    assert resp.status_code == 400
    assert "rejected" in resp.json()["error"].lower()


@pytest.mark.asyncio
async def test_generate_episode_art_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/ai/generate-episode-art",
        json={"ideaId": "idea-1", "imagePrompt": "Scene."},
    )
    assert resp.status_code == 401
