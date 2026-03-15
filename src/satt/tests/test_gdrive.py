"""Tests for gdrive.py and the /api/postproduction/scan routes.

All Google Drive API calls are mocked — no real network calls are made.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from httpx import AsyncClient

from satt.config import get_settings
from satt.database import get_db
from satt.gdrive import _asset_entry, _match_files, _prefix_match, build_asset_inventory, delete_file, upload_file_to_folder
from satt.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _headers() -> dict:
    settings = get_settings()
    payload = {
        "user_id": 1,
        "username": "testuser",
        "is_admin": False,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


def _full_config() -> dict:
    return {
        "gdriveFolderShowRecordings": "folder_show_recordings_id",
        "clientId": "fake-client-id",
        "clientSecret": "fake-client-secret",
        "refreshToken": "fake-refresh-token",
    }


def _fake_settings():
    s = MagicMock()
    s.google_oauth_client_id = "fake-client-id"
    s.google_oauth_client_secret = "fake-client-secret"
    s.google_oauth_refresh_token = "fake-refresh-token"
    return s


def _empty_settings():
    s = MagicMock()
    s.google_oauth_client_id = ""
    s.google_oauth_client_secret = ""
    s.google_oauth_refresh_token = ""
    return s


async def _override_get_db():
    yield AsyncMock()


# ---------------------------------------------------------------------------
# Unit: _match_files
# ---------------------------------------------------------------------------


def test_match_files_exact_match():
    files = [
        {"id": "abc", "name": "EP001_Test_2026-01-10.wav", "modifiedTime": "2026-01-10T18:00:00Z"},
        {"id": "def", "name": "EP002_Other_2026-01-10.wav", "modifiedTime": "2026-01-10T18:00:00Z"},
    ]
    result = _match_files(files, "EP001_Test_2026-01-10", "wav")
    assert len(result) == 1
    assert result[0]["id"] == "abc"


def test_match_files_no_match():
    files = [{"id": "abc", "name": "EP002_Other_2026-01-10.wav", "modifiedTime": "2026-01-10T18:00:00Z"}]
    result = _match_files(files, "EP001_Test_2026-01-10", "wav")
    assert result == []


def test_match_files_case_insensitive():
    files = [{"id": "abc", "name": "EP001_Test_2026-01-10.WAV", "modifiedTime": "2026-01-10T18:00:00Z"}]
    result = _match_files(files, "EP001_Test_2026-01-10", "wav")
    assert len(result) == 1


def test_match_files_multiple_matches():
    files = [
        {"id": "abc", "name": "EP001_Test_2026-01-10.wav", "modifiedTime": "2026-01-10T18:00:00Z"},
        {"id": "xyz", "name": "EP001_Test_2026-01-10.wav", "modifiedTime": "2026-01-10T19:00:00Z"},
    ]
    result = _match_files(files, "EP001_Test_2026-01-10", "wav")
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Unit: _asset_entry
# ---------------------------------------------------------------------------


def test_asset_entry_not_present():
    assert _asset_entry([]) == {"present": False}


def test_asset_entry_present():
    entry = _asset_entry([{"id": "fileid", "name": "foo.wav", "modifiedTime": "2026-01-10T18:00:00Z"}])
    assert entry["present"] is True
    assert entry["drive_file_id"] == "fileid"
    assert entry["modified"] == "2026-01-10T18:00:00Z"


def test_asset_entry_conflict():
    matches = [
        {"id": "a", "name": "foo.wav", "modifiedTime": "2026-01-10T18:00:00Z"},
        {"id": "b", "name": "foo.wav", "modifiedTime": "2026-01-10T19:00:00Z"},
    ]
    entry = _asset_entry(matches)
    assert entry["present"] is False
    assert entry.get("conflict") is True


# ---------------------------------------------------------------------------
# Unit: build_asset_inventory (mocked list_folder_files + token)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_asset_inventory_all_present():
    key = "EP001_Test_2026-01-10"
    episode_folder_id = "ep-folder-id"
    episode_files = [
        {"id": "r1", "name": f"Raw_Dog_{key}.wav", "modifiedTime": "2026-01-10T18:00:00Z"},
        {"id": "trog1", "name": f"Trog_{key}.wav", "modifiedTime": "2026-01-10T18:00:00Z"},
        {"id": "rocket1", "name": f"Rocket_{key}.wav", "modifiedTime": "2026-01-10T18:00:00Z"},
        {"id": "f1", "name": f"{key}.mp3", "modifiedTime": "2026-01-10T20:00:00Z"},
        {"id": "t1", "name": f"Transcript_{key}.txt", "modifiedTime": "2026-01-10T19:00:00Z"},
        {"id": "t2", "name": f"Transcript_{key}.json", "modifiedTime": "2026-01-10T19:00:00Z"},
        {"id": "a1", "name": f"Cover_Art_{key}.png", "modifiedTime": "2026-01-10T21:00:00Z"},
        {"id": "d1", "name": f"Art_Direction_{key}.json", "modifiedTime": "2026-01-10T21:00:00Z"},
    ]

    with patch("satt.gdrive.get_drive_access_token", new=AsyncMock(return_value="fake_token")):
        with patch("satt.gdrive.find_episode_folder", new=AsyncMock(return_value=episode_folder_id)):
            with patch("satt.gdrive.list_folder_files", new=AsyncMock(return_value=episode_files)):
                result = await build_asset_inventory("slot1", key, _full_config())

    assert result["episode_folder_id"] == episode_folder_id
    assert result["raw_audio"]["present"] is True
    assert result["raw_trog"]["present"] is True
    assert result["raw_rocket"]["present"] is True
    assert result["finished_audio"]["present"] is True
    assert result["transcript_txt"]["present"] is True
    assert result["transcript_json"]["present"] is True
    assert result["album_art"]["present"] is True
    assert result["art_direction"]["present"] is True
    assert "scanned_at" in result


@pytest.mark.asyncio
async def test_build_asset_inventory_all_missing():
    """When no episode folder is found, all assets are absent."""
    key = "EP001_Missing_2026-01-10"

    with patch("satt.gdrive.get_drive_access_token", new=AsyncMock(return_value="fake_token")):
        with patch("satt.gdrive.find_episode_folder", new=AsyncMock(return_value=None)):
            result = await build_asset_inventory("slot1", key, _full_config())

    assert result["episode_folder_id"] is None
    assert result["raw_audio"]["present"] is False
    assert result["raw_trog"]["present"] is False
    assert result["raw_rocket"]["present"] is False
    assert result["finished_audio"]["present"] is False
    assert result["transcript_txt"]["present"] is False
    assert result["transcript_json"]["present"] is False
    assert result["album_art"]["present"] is False
    assert result["art_direction"]["present"] is False


@pytest.mark.asyncio
async def test_build_asset_inventory_conflict():
    key = "EP001_Conflict_2026-01-10"
    episode_folder_id = "ep-folder-id"
    duplicate = [
        {"id": "a", "name": f"Raw_Dog_{key}.wav", "modifiedTime": "2026-01-10T18:00:00Z"},
        {"id": "b", "name": f"Raw_Dog_{key}.wav", "modifiedTime": "2026-01-10T19:00:00Z"},
    ]

    with patch("satt.gdrive.get_drive_access_token", new=AsyncMock(return_value="fake_token")):
        with patch("satt.gdrive.find_episode_folder", new=AsyncMock(return_value=episode_folder_id)):
            with patch("satt.gdrive.list_folder_files", new=AsyncMock(return_value=duplicate)):
                result = await build_asset_inventory("slot1", key, _full_config())

    assert result["raw_audio"]["present"] is False
    assert result["raw_audio"].get("conflict") is True


# ---------------------------------------------------------------------------
# Route: POST /api/postproduction/scan — 400 when not configured
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_all_returns_400_when_folders_not_configured(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db
    with patch("satt.routes.postproduction.get_config", new=AsyncMock(return_value={})):
        with patch("satt.routes.postproduction.get_settings", return_value=_empty_settings()):
            resp = await client.post("/api/postproduction/scan", headers=_headers())
    app.dependency_overrides.clear()
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_scan_all_returns_400_when_oauth_not_set(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db
    db_cfg = {
        "gdriveFolderShowRecordings": "folder_show_recordings_id",
    }
    with patch("satt.routes.postproduction.get_config", new=AsyncMock(return_value=db_cfg)):
        with patch("satt.routes.postproduction.get_settings", return_value=_empty_settings()):
            resp = await client.post("/api/postproduction/scan", headers=_headers())
    app.dependency_overrides.clear()
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Route: POST /api/postproduction/scan — scans eligible slots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_all_calls_build_for_each_eligible_slot(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db

    slots = [
        {"slot_id": "slot_a", "production_file_key": "EP001_A_2026-01-10"},
        {"slot_id": "slot_b", "production_file_key": "EP002_B_2026-02-07"},
    ]
    fake_inventory = {"scanned_at": "2026-03-06T00:00:00+00:00", "raw_audio": {"present": False}}

    with patch("satt.routes.postproduction.get_config", new=AsyncMock(return_value=_full_config())):
        with patch("satt.routes.postproduction.get_settings", return_value=_fake_settings()):
            with patch("satt.routes.postproduction.get_slots_for_scan", new=AsyncMock(return_value=slots)):
                with patch("satt.routes.postproduction.build_asset_inventory", new=AsyncMock(return_value=fake_inventory)):
                    with patch("satt.routes.postproduction.set_asset_inventory", new=AsyncMock()):
                        resp = await client.post("/api/postproduction/scan", headers=_headers())

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["scanned"] == 2
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_scan_all_captures_per_slot_errors(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db

    slots = [{"slot_id": "slot_err", "production_file_key": "EP001_Err"}]

    async def boom(slot_id, key, config):
        raise RuntimeError("Drive API unreachable")

    with patch("satt.routes.postproduction.get_config", new=AsyncMock(return_value=_full_config())):
        with patch("satt.routes.postproduction.get_settings", return_value=_fake_settings()):
            with patch("satt.routes.postproduction.get_slots_for_scan", new=AsyncMock(return_value=slots)):
                with patch("satt.routes.postproduction.build_asset_inventory", new=AsyncMock(side_effect=boom)):
                    with patch("satt.routes.postproduction.set_asset_inventory", new=AsyncMock()):
                        resp = await client.post("/api/postproduction/scan", headers=_headers())

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["scanned"] == 0
    assert len(data["errors"]) == 1
    assert data["errors"][0]["slotId"] == "slot_err"


# ---------------------------------------------------------------------------
# Route: auth required
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_all_requires_auth(client: AsyncClient):
    resp = await client.post("/api/postproduction/scan")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_scan_single_requires_auth(client: AsyncClient):
    resp = await client.post("/api/postproduction/slot123/scan")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_scan_single_returns_400_when_not_configured(client: AsyncClient):
    app.dependency_overrides[get_db] = _override_get_db
    with patch("satt.routes.postproduction.get_config", new=AsyncMock(return_value={})):
        with patch("satt.routes.postproduction.get_settings", return_value=_empty_settings()):
            resp = await client.post("/api/postproduction/slot123/scan", headers=_headers())
    app.dependency_overrides.clear()
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# list_folder_files: mocked httpx response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_folder_files_parses_response():
    from satt.gdrive import list_folder_files

    files_data = [
        {"id": "fileid1", "name": "EP001_Test.wav", "modifiedTime": "2026-01-10T18:00:00Z"},
        {"id": "fileid2", "name": "EP002_Other.wav", "modifiedTime": "2026-01-10T19:00:00Z"},
    ]

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"files": files_data})

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("satt.gdrive.httpx.AsyncClient", return_value=mock_client):
        result = await list_folder_files("fake_token", "folder_id_123")

    assert len(result) == 2
    assert result[0]["id"] == "fileid1"
    assert result[1]["name"] == "EP002_Other.wav"
    call_kwargs = mock_client.get.call_args
    assert "folder_id_123" in call_kwargs[1]["params"]["q"]


# ---------------------------------------------------------------------------
# upload_file_to_folder: mocked httpx
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_file_to_folder_sends_multipart_request():
    fake_file_id = "uploaded-file-id-xyz"
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"id": fake_file_id})

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("satt.gdrive.httpx.AsyncClient", return_value=mock_client):
        result = await upload_file_to_folder(
            access_token="fake-token",
            folder_id="folder-cover-art",
            filename="EP042_Test_2026-03-06.png",
            content=png_bytes,
        )

    assert result == fake_file_id
    call_kwargs = mock_client.post.call_args
    # Verify correct upload endpoint and params
    assert "upload/drive/v3/files" in call_kwargs[0][0]
    assert call_kwargs[1]["params"]["uploadType"] == "multipart"
    assert call_kwargs[1]["params"]["supportsAllDrives"] == "true"
    # Verify multipart/related content-type header
    assert "multipart/related" in call_kwargs[1]["headers"]["Content-Type"]
    # Verify body contains metadata and image bytes
    body = call_kwargs[1]["content"]
    assert b"EP042_Test_2026-03-06.png" in body
    assert b"folder-cover-art" in body
    assert png_bytes in body


@pytest.mark.asyncio
async def test_upload_file_to_folder_returns_file_id():
    """Verify the Drive file ID from the response JSON is returned."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"id": "specific-id-123", "name": "test.png"})

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("satt.gdrive.httpx.AsyncClient", return_value=mock_client):
        result = await upload_file_to_folder("tok", "folder", "file.png", b"data")

    assert result == "specific-id-123"


# ---------------------------------------------------------------------------
# delete_file: mocked httpx
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_file_sends_delete_request():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.delete = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("satt.gdrive.httpx.AsyncClient", return_value=mock_client):
        await delete_file("fake-token", "file-id-to-delete")

    call_args = mock_client.delete.call_args
    assert "file-id-to-delete" in call_args[0][0]
    assert call_args[1]["params"]["supportsAllDrives"] == "true"
    assert "fake-token" in call_args[1]["headers"]["Authorization"]
