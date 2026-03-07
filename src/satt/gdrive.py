"""Google Drive API integration — raw httpx calls, no Google SDK.

Authentication uses a service account JWT (RS256) exchanged for an OAuth2
access token. The token is cached in-process for 1 hour minus a 60-second
buffer to avoid using an about-to-expire token.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone

import httpx
import jwt as pyjwt

_TOKEN_CACHE: dict = {}
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
_SCOPE = "https://www.googleapis.com/auth/drive.readonly"


async def get_drive_access_token(service_account_json: str) -> str:
    """Return a cached or fresh OAuth2 access token for the service account."""
    now = time.time()
    cached = _TOKEN_CACHE.get("entry")
    if cached and cached["expiry"] > now + 60:
        return cached["token"]

    sa = json.loads(service_account_json)
    iat = int(now)
    exp = iat + 3600

    assertion = pyjwt.encode(
        {
            "iss": sa["client_email"],
            "scope": _SCOPE,
            "aud": _GOOGLE_TOKEN_URL,
            "iat": iat,
            "exp": exp,
        },
        sa["private_key"],
        algorithm="RS256",
    )

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        )
        resp.raise_for_status()
        token_data = resp.json()

    token = token_data["access_token"]
    _TOKEN_CACHE["entry"] = {"token": token, "expiry": now + 3600}
    return token


async def list_folder_files(access_token: str, folder_id: str) -> list[dict]:
    """List files in a Drive folder. Returns list of {id, name, modifiedTime}."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            _DRIVE_FILES_URL,
            params={
                "q": f"'{folder_id}' in parents and trashed = false",
                "fields": "files(id,name,modifiedTime)",
                "pageSize": 1000,
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


async def build_asset_inventory(
    slot_id: str, production_file_key: str, config: dict
) -> dict:
    """Scan all four Drive folders and return an asset_inventory dict.

    config must contain:
      - serviceAccountJson (str): the full service account JSON
      - gdriveFolderRawAudio (str): folder ID
      - gdriveFolderFinishedAudio (str): folder ID
      - gdriveFolderTranscripts (str): folder ID
      - gdriveFolderCoverArt (str): folder ID
    """
    access_token = await get_drive_access_token(config["serviceAccountJson"])

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
