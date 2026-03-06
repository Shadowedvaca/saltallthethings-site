"""Tests for GET /api/postproduction and PUT /api/postproduction/{slot_id}/key."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from satt.config import get_settings
from satt.crud import set_asset_inventory, set_production_file_key


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


# Slots with past record_date (included in queue)
PAST_SLOT_1 = {
    "id": "pp_slot_past_1",
    "episodeNumber": "EP001",
    "episodeNum": 1,
    "recordDate": "2026-01-10",
    "releaseDate": "2026-01-17",
    "isRollout": False,
    "releaseDateOverride": None,
}

PAST_SLOT_2 = {
    "id": "pp_slot_past_2",
    "episodeNumber": "EP002",
    "episodeNum": 2,
    "recordDate": "2026-02-07",
    "releaseDate": "2026-02-14",
    "isRollout": False,
    "releaseDateOverride": None,
}

# Slot with future record_date (excluded from queue)
FUTURE_SLOT = {
    "id": "pp_slot_future",
    "episodeNumber": "EP099",
    "episodeNum": 99,
    "recordDate": "2026-12-31",
    "releaseDate": "2027-01-07",
    "isRollout": False,
    "releaseDateOverride": None,
}

IDEA = {
    "id": "pp_idea_1",
    "titles": ["War Within Seasons Ranked"],
    "selectedTitle": "War Within Seasons Ranked",
    "summary": "We rank the WoW seasons.",
    "outline": [],
    "status": "draft",
    "imageFileId": None,
    "rawNotes": None,
    "createdAt": "2026-01-01T00:00:00Z",
    "updatedAt": "2026-01-01T00:00:00Z",
}


# ---------------------------------------------------------------------------
# Filter: only past slots returned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_excludes_future_slots(db_client: AsyncClient):
    await db_client.put(
        "/api/data/showSlots",
        json=[PAST_SLOT_1, FUTURE_SLOT],
        headers=_headers(),
    )
    resp = await db_client.get("/api/postproduction", headers=_headers())
    assert resp.status_code == 200
    ids = [row["slotId"] for row in resp.json()]
    assert PAST_SLOT_1["id"] in ids
    assert FUTURE_SLOT["id"] not in ids


@pytest.mark.asyncio
async def test_queue_includes_past_slots(db_client: AsyncClient):
    await db_client.put(
        "/api/data/showSlots",
        json=[PAST_SLOT_1, PAST_SLOT_2],
        headers=_headers(),
    )
    resp = await db_client.get("/api/postproduction", headers=_headers())
    assert resp.status_code == 200
    ids = [row["slotId"] for row in resp.json()]
    assert PAST_SLOT_1["id"] in ids
    assert PAST_SLOT_2["id"] in ids


# ---------------------------------------------------------------------------
# Ordering: desc by record_date
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_ordered_desc_by_record_date(db_client: AsyncClient):
    await db_client.put(
        "/api/data/showSlots",
        json=[PAST_SLOT_1, PAST_SLOT_2],
        headers=_headers(),
    )
    resp = await db_client.get("/api/postproduction", headers=_headers())
    assert resp.status_code == 200
    rows = resp.json()
    dates = [row["recordDate"] for row in rows]
    assert dates == sorted(dates, reverse=True)


# ---------------------------------------------------------------------------
# PUT key endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_key_updates_and_returns_row(db_client: AsyncClient):
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1], headers=_headers()
    )
    resp = await db_client.put(
        f"/api/postproduction/{PAST_SLOT_1['id']}/key",
        json={"productionFileKey": "EP001_War-Within_2026-01-10"},
        headers=_headers(),
    )
    assert resp.status_code == 200
    row = resp.json()
    assert row["slotId"] == PAST_SLOT_1["id"]
    assert row["productionFileKey"] == "EP001_War-Within_2026-01-10"


@pytest.mark.asyncio
async def test_put_key_reflected_in_get(db_client: AsyncClient):
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1], headers=_headers()
    )
    await db_client.put(
        f"/api/postproduction/{PAST_SLOT_1['id']}/key",
        json={"productionFileKey": "EP001_Test_2026-01-10"},
        headers=_headers(),
    )
    resp = await db_client.get("/api/postproduction", headers=_headers())
    rows = {r["slotId"]: r for r in resp.json()}
    assert rows[PAST_SLOT_1["id"]]["productionFileKey"] == "EP001_Test_2026-01-10"


# ---------------------------------------------------------------------------
# nextStep logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_next_step_set_key_when_no_key(db_client: AsyncClient):
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1], headers=_headers()
    )
    resp = await db_client.get("/api/postproduction", headers=_headers())
    rows = {r["slotId"]: r for r in resp.json()}
    assert rows[PAST_SLOT_1["id"]]["nextStep"] == "set_key"


@pytest.mark.asyncio
async def test_next_step_upload_raw_when_key_set_no_audio(
    db_client: AsyncClient, db_session: AsyncSession
):
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1], headers=_headers()
    )
    await set_production_file_key(db_session, PAST_SLOT_1["id"], "EP001_Test")
    await set_asset_inventory(
        db_session,
        PAST_SLOT_1["id"],
        {"raw_audio": {"present": False}},
    )
    resp = await db_client.get("/api/postproduction", headers=_headers())
    rows = {r["slotId"]: r for r in resp.json()}
    assert rows[PAST_SLOT_1["id"]]["nextStep"] == "upload_raw"


@pytest.mark.asyncio
async def test_next_step_transcribe_when_no_transcript(
    db_client: AsyncClient, db_session: AsyncSession
):
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1], headers=_headers()
    )
    await set_production_file_key(db_session, PAST_SLOT_1["id"], "EP001_Test")
    await set_asset_inventory(
        db_session,
        PAST_SLOT_1["id"],
        {
            "raw_audio": {"present": True, "modified": "2026-01-10T18:00:00Z"},
            "transcript_txt": {"present": False},
        },
    )
    resp = await db_client.get("/api/postproduction", headers=_headers())
    rows = {r["slotId"]: r for r in resp.json()}
    assert rows[PAST_SLOT_1["id"]]["nextStep"] == "transcribe"


@pytest.mark.asyncio
async def test_next_step_retranscribe_when_audio_newer_than_transcript(
    db_client: AsyncClient, db_session: AsyncSession
):
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1], headers=_headers()
    )
    await set_production_file_key(db_session, PAST_SLOT_1["id"], "EP001_Test")
    await set_asset_inventory(
        db_session,
        PAST_SLOT_1["id"],
        {
            "raw_audio": {"present": True, "modified": "2026-01-10T20:00:00Z"},
            "transcript_txt": {"present": True, "modified": "2026-01-10T18:00:00Z"},
        },
    )
    resp = await db_client.get("/api/postproduction", headers=_headers())
    rows = {r["slotId"]: r for r in resp.json()}
    assert rows[PAST_SLOT_1["id"]]["nextStep"] == "retranscribe"


@pytest.mark.asyncio
async def test_next_step_generate_art_when_no_album_art(
    db_client: AsyncClient, db_session: AsyncSession
):
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1], headers=_headers()
    )
    await set_production_file_key(db_session, PAST_SLOT_1["id"], "EP001_Test")
    await set_asset_inventory(
        db_session,
        PAST_SLOT_1["id"],
        {
            "raw_audio": {"present": True, "modified": "2026-01-10T18:00:00Z"},
            "transcript_txt": {"present": True, "modified": "2026-01-10T20:00:00Z"},
            "album_art": {"present": False},
        },
    )
    resp = await db_client.get("/api/postproduction", headers=_headers())
    rows = {r["slotId"]: r for r in resp.json()}
    assert rows[PAST_SLOT_1["id"]]["nextStep"] == "generate_art"


@pytest.mark.asyncio
async def test_next_step_awaiting_editor_when_no_finished_audio(
    db_client: AsyncClient, db_session: AsyncSession
):
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1], headers=_headers()
    )
    await set_production_file_key(db_session, PAST_SLOT_1["id"], "EP001_Test")
    await set_asset_inventory(
        db_session,
        PAST_SLOT_1["id"],
        {
            "raw_audio": {"present": True, "modified": "2026-01-10T18:00:00Z"},
            "transcript_txt": {"present": True, "modified": "2026-01-10T20:00:00Z"},
            "album_art": {"present": True},
            "finished_audio": {"present": False},
        },
    )
    resp = await db_client.get("/api/postproduction", headers=_headers())
    rows = {r["slotId"]: r for r in resp.json()}
    assert rows[PAST_SLOT_1["id"]]["nextStep"] == "awaiting_editor"


@pytest.mark.asyncio
async def test_next_step_complete_when_all_assets_present(
    db_client: AsyncClient, db_session: AsyncSession
):
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1], headers=_headers()
    )
    await set_production_file_key(db_session, PAST_SLOT_1["id"], "EP001_Test")
    await set_asset_inventory(
        db_session,
        PAST_SLOT_1["id"],
        {
            "raw_audio": {"present": True, "modified": "2026-01-10T18:00:00Z"},
            "transcript_txt": {"present": True, "modified": "2026-01-10T20:00:00Z"},
            "album_art": {"present": True},
            "finished_audio": {"present": True},
        },
    )
    resp = await db_client.get("/api/postproduction", headers=_headers())
    rows = {r["slotId"]: r for r in resp.json()}
    assert rows[PAST_SLOT_1["id"]]["nextStep"] == "complete"


# ---------------------------------------------------------------------------
# Idea fields included when slot is assigned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_includes_idea_fields_when_assigned(db_client: AsyncClient):
    await db_client.put("/api/data/ideas", json=[IDEA], headers=_headers())
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1], headers=_headers()
    )
    await db_client.put(
        "/api/data/assignments",
        json={PAST_SLOT_1["id"]: IDEA["id"]},
        headers=_headers(),
    )
    resp = await db_client.get("/api/postproduction", headers=_headers())
    rows = {r["slotId"]: r for r in resp.json()}
    row = rows[PAST_SLOT_1["id"]]
    assert row["ideaId"] == IDEA["id"]
    assert row["selectedTitle"] == IDEA["selectedTitle"]
    assert row["ideaStatus"] == IDEA["status"]


@pytest.mark.asyncio
async def test_queue_idea_fields_null_when_unassigned(db_client: AsyncClient):
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1], headers=_headers()
    )
    resp = await db_client.get("/api/postproduction", headers=_headers())
    rows = {r["slotId"]: r for r in resp.json()}
    row = rows[PAST_SLOT_1["id"]]
    assert row["ideaId"] is None
    assert row["selectedTitle"] is None


# ---------------------------------------------------------------------------
# Auth required
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_postproduction_requires_auth(db_client: AsyncClient):
    resp = await db_client.get("/api/postproduction")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_put_key_requires_auth(db_client: AsyncClient):
    resp = await db_client.put(
        f"/api/postproduction/{PAST_SLOT_1['id']}/key",
        json={"productionFileKey": "EP001_Test"},
    )
    assert resp.status_code == 401
