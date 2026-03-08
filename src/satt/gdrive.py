"""Google Drive API integration — raw httpx calls, no Google SDK.

Authentication uses an OAuth2 refresh token exchanged for a short-lived
access token. The access token is cached in-process and refreshed when it
expires (or is within 60 seconds of expiry).
"""

from __future__ import annotations

import asyncio
import base64
import json as _json
import time
from datetime import datetime, timezone

import httpx

_TOKEN_CACHE: dict = {}
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"


async def get_drive_access_token(
    client_id: str, client_secret: str, refresh_token: str
) -> str:
    """Return a cached or fresh OAuth2 access token via refresh token exchange."""
    now = time.time()
    cached = _TOKEN_CACHE.get("entry")
    if cached and cached["expiry"] > now + 60:
        return cached["token"]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            },
        )
        resp.raise_for_status()
        token_data = resp.json()

    token = token_data["access_token"]
    expires_in = token_data.get("expires_in", 3600)
    _TOKEN_CACHE["entry"] = {"token": token, "expiry": now + expires_in}
    return token


async def fetch_file_content(access_token: str, file_id: str) -> str:
    """Download a file from Drive and return its text content."""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            params={"alt": "media", "supportsAllDrives": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.text


async def list_folder_files(access_token: str, folder_id: str) -> list[dict]:
    """List files in a Drive folder. Returns list of {id, name, modifiedTime}."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            _DRIVE_FILES_URL,
            params={
                "q": f"'{folder_id}' in parents and trashed = false",
                "fields": "files(id,name,modifiedTime)",
                "pageSize": 1000,
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json().get("files", [])


def _match_files(files: list[dict], key: str, ext: str) -> list[dict]:
    """Return files whose name matches key.ext (case-insensitive)."""
    target = f"{key}.{ext}".lower()
    return [f for f in files if f["name"].lower() == target]


def _asset_entry(matches: list[dict]) -> dict:
    if len(matches) == 0:
        return {"present": False}
    if len(matches) > 1:
        return {"present": False, "conflict": True}
    m = matches[0]
    return {
        "present": True,
        "drive_file_id": m["id"],
        "modified": m.get("modifiedTime"),
    }


async def fetch_image_as_base64(access_token: str, file_id: str) -> tuple[str, str]:
    """Download a Drive image file. Returns (base64_data, mime_type)."""
    async with httpx.AsyncClient(timeout=60) as client:
        meta = await client.get(
            f"{_DRIVE_FILES_URL}/{file_id}",
            params={"fields": "mimeType", "supportsAllDrives": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        meta.raise_for_status()
        mime_type = meta.json().get("mimeType", "image/jpeg")

        resp = await client.get(
            f"{_DRIVE_FILES_URL}/{file_id}",
            params={"alt": "media", "supportsAllDrives": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return base64.b64encode(resp.content).decode(), mime_type


async def upload_file_to_folder(
    access_token: str,
    folder_id: str,
    filename: str,
    content: bytes,
    mime_type: str = "image/png",
) -> str:
    """Upload a file to a Drive folder using multipart upload. Returns the new file ID."""
    boundary = "SattDriveBoundary42"
    metadata = _json.dumps({"name": filename, "parents": [folder_id]}).encode()

    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
        + metadata
        + f"\r\n--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n".encode()
        + content
        + f"\r\n--{boundary}--".encode()
    )

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://www.googleapis.com/upload/drive/v3/files",
            params={"uploadType": "multipart", "supportsAllDrives": "true"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
            content=body,
        )
    resp.raise_for_status()
    return resp.json()["id"]


async def delete_file(access_token: str, file_id: str) -> None:
    """Delete a file from Google Drive."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.delete(
            f"{_DRIVE_FILES_URL}/{file_id}",
            params={"supportsAllDrives": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    resp.raise_for_status()


async def build_asset_inventory(
    slot_id: str, production_file_key: str, config: dict
) -> dict:
    """Scan all four Drive folders and return an asset_inventory dict.

    config must contain:
      - clientId (str): OAuth2 client ID
      - clientSecret (str): OAuth2 client secret
      - refreshToken (str): OAuth2 refresh token
      - gdriveFolderRawAudio (str): folder ID
      - gdriveFolderFinishedAudio (str): folder ID
      - gdriveFolderTranscripts (str): folder ID
      - gdriveFolderCoverArt (str): folder ID
    """
    access_token = await get_drive_access_token(
        config["clientId"], config["clientSecret"], config["refreshToken"]
    )

    raw_files, finished_files, transcript_files, art_files = await asyncio.gather(
        list_folder_files(access_token, config["gdriveFolderRawAudio"]),
        list_folder_files(access_token, config["gdriveFolderFinishedAudio"]),
        list_folder_files(access_token, config["gdriveFolderTranscripts"]),
        list_folder_files(access_token, config["gdriveFolderCoverArt"]),
    )

    key = production_file_key
    return {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "raw_audio": _asset_entry(_match_files(raw_files, key, "wav")),
        "finished_audio": _asset_entry(_match_files(finished_files, key, "mp3")),
        "transcript_txt": _asset_entry(_match_files(transcript_files, key, "txt")),
        "transcript_json": _asset_entry(_match_files(transcript_files, key, "json")),
        "album_art": _asset_entry(_match_files(art_files, key, "png")),
    }
