"""Tests for GET /api/postproduction and PUT /api/postproduction/{slot_id}/key."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import satt.routes.postproduction as postproduction_routes
from satt.config import get_settings
from satt.crud import (
    TranscriptionJobConflictError,
    TranscriptionJobNotFoundError,
    claim_transcription_job,
    get_claimable_transcription_jobs,
    queue_transcription_job,
    reset_stale_transcription_job,
    set_asset_inventory,
    set_production_file_key,
    set_transcription_job,
    update_transcription_claim,
)


def _headers(*, is_admin: bool = False) -> dict:
    settings = get_settings()
    payload = {
        "user_id": 1,
        "username": "testuser",
        "is_admin": is_admin,
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
    assert row["ideaStatus"] == "scheduled"


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


# ---------------------------------------------------------------------------
# Safe, targeted transcription recovery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_is_idempotent_and_claim_is_atomic(
    db_client: AsyncClient, db_session: AsyncSession
):
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1], headers=_headers()
    )
    await set_production_file_key(db_session, PAST_SLOT_1["id"], "EP001_Test")

    first = await db_client.post(
        f"/api/postproduction/{PAST_SLOT_1['id']}/transcribe", headers=_headers()
    )
    second = await db_client.post(
        f"/api/postproduction/{PAST_SLOT_1['id']}/transcribe", headers=_headers()
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["transcriptionJob"]["jobId"] == second.json()["transcriptionJob"]["jobId"]

    claim = await db_client.post(
        f"/api/postproduction/{PAST_SLOT_1['id']}/transcribe-claim",
        json={"workerId": "watcher-one"},
        headers=_headers(is_admin=True),
    )
    assert claim.status_code == 200
    assert claim.json()["claimToken"]

    competing = await db_client.post(
        f"/api/postproduction/{PAST_SLOT_1['id']}/transcribe-claim",
        json={"workerId": "watcher-two"},
        headers=_headers(is_admin=True),
    )
    assert competing.status_code == 409
    assert "active watcher lease" in competing.json()["detail"]


@pytest.mark.asyncio
async def test_claim_token_is_required_and_hidden_from_browser_queue(
    db_client: AsyncClient, db_session: AsyncSession
):
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1], headers=_headers()
    )
    await set_production_file_key(db_session, PAST_SLOT_1["id"], "EP001_Test")
    await queue_transcription_job(db_session, PAST_SLOT_1["id"])
    claim = await claim_transcription_job(
        db_session, PAST_SLOT_1["id"], "watcher-one"
    )

    queue = await db_client.get("/api/postproduction", headers=_headers())
    visible = queue.json()[0]["transcriptionJob"]
    assert visible["status"] == "in_progress"
    assert "claimToken" not in visible

    wrong_owner = await db_client.put(
        f"/api/postproduction/{PAST_SLOT_1['id']}/transcribe-status",
        json={"status": "done", "claimToken": "wrong-token"},
        headers=_headers(is_admin=True),
    )
    assert wrong_owner.status_code == 409

    completed = await db_client.put(
        f"/api/postproduction/{PAST_SLOT_1['id']}/transcribe-status",
        json={"status": "done", "claimToken": claim["claimToken"]},
        headers=_headers(is_admin=True),
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "done"
    assert "claimToken" not in completed.json()


@pytest.mark.asyncio
async def test_manual_reset_is_admin_only_and_rejects_active_job(
    db_client: AsyncClient, db_session: AsyncSession
):
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1], headers=_headers()
    )
    await set_production_file_key(db_session, PAST_SLOT_1["id"], "EP001_Test")
    await queue_transcription_job(db_session, PAST_SLOT_1["id"])
    await claim_transcription_job(db_session, PAST_SLOT_1["id"], "watcher-one")

    forbidden = await db_client.post(
        f"/api/postproduction/{PAST_SLOT_1['id']}/transcribe-reset",
        headers=_headers(),
    )
    assert forbidden.status_code == 403

    active = await db_client.post(
        f"/api/postproduction/{PAST_SLOT_1['id']}/transcribe-reset",
        headers=_headers(is_admin=True),
    )
    assert active.status_code == 409
    assert "active watcher lease" in active.json()["detail"]


@pytest.mark.asyncio
async def test_watcher_endpoints_require_admin(
    db_client: AsyncClient, db_session: AsyncSession
):
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1], headers=_headers()
    )
    await set_production_file_key(db_session, PAST_SLOT_1["id"], "EP001_Test")
    await queue_transcription_job(db_session, PAST_SLOT_1["id"])
    listed = await db_client.get(
        "/api/postproduction/transcription-jobs", headers=_headers()
    )
    claimed = await db_client.post(
        f"/api/postproduction/{PAST_SLOT_1['id']}/transcribe-claim",
        json={"workerId": "watcher-one"},
        headers=_headers(),
    )
    updated = await db_client.put(
        f"/api/postproduction/{PAST_SLOT_1['id']}/transcribe-status",
        json={"status": "done", "claimToken": "not-owned"},
        headers=_headers(),
    )
    assert listed.status_code == claimed.status_code == updated.status_code == 403


@pytest.mark.asyncio
async def test_targeted_reset_changes_only_selected_stale_job(
    db_client: AsyncClient, db_session: AsyncSession
):
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1, PAST_SLOT_2], headers=_headers()
    )
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    await set_transcription_job(
        db_session,
        PAST_SLOT_1["id"],
        {
            "jobId": "job-one",
            "status": "in_progress",
            "claimToken": "old-claim",
            "leaseExpiresAt": old,
        },
    )
    await set_transcription_job(
        db_session,
        PAST_SLOT_2["id"],
        {
            "jobId": "job-two",
            "status": "in_progress",
            "claimToken": "active-claim",
            "leaseExpiresAt": future,
        },
    )

    reset = await db_client.post(
        f"/api/postproduction/{PAST_SLOT_1['id']}/transcribe-reset",
        headers=_headers(is_admin=True),
    )
    assert reset.status_code == 200
    assert reset.json()["transcriptionJob"]["status"] == "pending"
    assert reset.json()["transcriptionJob"]["resetBy"] == "testuser"

    queue = await db_client.get("/api/postproduction", headers=_headers())
    jobs = {row["slotId"]: row["transcriptionJob"] for row in queue.json()}
    assert jobs[PAST_SLOT_1["id"]]["status"] == "pending"
    assert jobs[PAST_SLOT_2["id"]]["status"] == "in_progress"
    assert jobs[PAST_SLOT_2["id"]]["isStale"] is False


@pytest.mark.asyncio
async def test_watcher_poll_and_claim_recover_only_stale_job(
    db_client: AsyncClient, db_session: AsyncSession
):
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1, PAST_SLOT_2], headers=_headers()
    )
    await set_production_file_key(db_session, PAST_SLOT_1["id"], "EP001_Test")
    await set_production_file_key(db_session, PAST_SLOT_2["id"], "EP002_Test")
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    await set_transcription_job(
        db_session,
        PAST_SLOT_1["id"],
        {
            "jobId": "stale-job",
            "status": "in_progress",
            "claimToken": "expired-claim",
            "leaseExpiresAt": old,
            "recoveryCount": 0,
        },
    )
    await set_transcription_job(
        db_session,
        PAST_SLOT_2["id"],
        {
            "jobId": "active-job",
            "status": "in_progress",
            "claimToken": "active-claim",
            "leaseExpiresAt": future,
        },
    )

    poll = await db_client.get(
        "/api/postproduction/transcription-jobs",
        headers=_headers(is_admin=True),
    )
    assert poll.status_code == 200
    assert poll.json() == [
        {
            "slotId": PAST_SLOT_1["id"],
            "productionFileKey": "EP001_Test",
        }
    ]

    recovered = await db_client.post(
        f"/api/postproduction/{PAST_SLOT_1['id']}/transcribe-claim",
        json={"workerId": "replacement-watcher"},
        headers=_headers(is_admin=True),
    )
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "in_progress"
    assert recovered.json()["recoveryCount"] == 1
    assert recovered.json()["claimToken"] != "expired-claim"

    active = await db_client.post(
        f"/api/postproduction/{PAST_SLOT_2['id']}/transcribe-claim",
        json={"workerId": "replacement-watcher"},
        headers=_headers(is_admin=True),
    )
    assert active.status_code == 409


@pytest.mark.asyncio
async def test_atomic_job_helpers_reject_invalid_states(
    db_client: AsyncClient, db_session: AsyncSession
):
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1], headers=_headers()
    )

    with pytest.raises(TranscriptionJobNotFoundError, match="Slot not found"):
        await queue_transcription_job(db_session, "missing-slot")
    with pytest.raises(TranscriptionJobConflictError, match="Production file key"):
        await queue_transcription_job(db_session, PAST_SLOT_1["id"])

    await set_production_file_key(db_session, PAST_SLOT_1["id"], "EP001_Test")
    pending = await queue_transcription_job(db_session, PAST_SLOT_1["id"])
    assert await queue_transcription_job(db_session, PAST_SLOT_1["id"]) == pending

    claim = await claim_transcription_job(
        db_session, PAST_SLOT_1["id"], "watcher-one"
    )
    with pytest.raises(TranscriptionJobConflictError, match="active watcher lease"):
        await claim_transcription_job(db_session, PAST_SLOT_1["id"], "watcher-two")
    with pytest.raises(TranscriptionJobConflictError, match="already active"):
        await queue_transcription_job(db_session, PAST_SLOT_1["id"])
    with pytest.raises(TranscriptionJobConflictError, match="no longer active"):
        await update_transcription_claim(
            db_session, PAST_SLOT_1["id"], "wrong-token", "done"
        )
    with pytest.raises(TranscriptionJobConflictError, match="active watcher lease"):
        await reset_stale_transcription_job(
            db_session, PAST_SLOT_1["id"], "testuser"
        )

    await update_transcription_claim(
        db_session, PAST_SLOT_1["id"], claim["claimToken"], "done"
    )
    with pytest.raises(TranscriptionJobConflictError, match="not claimable"):
        await claim_transcription_job(db_session, PAST_SLOT_1["id"], "watcher-two")
    with pytest.raises(TranscriptionJobConflictError, match="not in progress"):
        await reset_stale_transcription_job(
            db_session, PAST_SLOT_1["id"], "testuser"
        )


@pytest.mark.asyncio
async def test_atomic_job_helpers_renew_finish_and_recover_with_metadata(
    db_client: AsyncClient, db_session: AsyncSession
):
    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1, PAST_SLOT_2], headers=_headers()
    )
    await set_production_file_key(db_session, PAST_SLOT_1["id"], "EP001_Test")
    await set_production_file_key(db_session, PAST_SLOT_2["id"], "EP002_Test")
    await queue_transcription_job(db_session, PAST_SLOT_1["id"])
    claim = await claim_transcription_job(
        db_session, PAST_SLOT_1["id"], "watcher-one"
    )
    renewed = await update_transcription_claim(
        db_session, PAST_SLOT_1["id"], claim["claimToken"], "in_progress"
    )
    assert renewed["leaseExpiresAt"]
    failed = await update_transcription_claim(
        db_session,
        PAST_SLOT_1["id"],
        claim["claimToken"],
        "failed",
        error="bounded failure",
    )
    assert failed["error"] == "bounded failure"
    assert "claimToken" not in failed

    stale_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    await set_transcription_job(
        db_session,
        PAST_SLOT_2["id"],
        {
            "status": "in_progress",
            "updatedAt": stale_time.isoformat(),
            "claimToken": "expired",
            "error": "old failure",
        },
    )
    claimable = await get_claimable_transcription_jobs(db_session)
    assert claimable == [
        {"slotId": PAST_SLOT_2["id"], "productionFileKey": "EP002_Test"}
    ]
    recovered = await claim_transcription_job(
        db_session, PAST_SLOT_2["id"], "watcher-two"
    )
    assert recovered["recoveryCount"] == 1
    assert recovered["recoveredAt"]
    assert "error" not in recovered
    reset_time = datetime.now(timezone.utc) + timedelta(minutes=10)
    reset = await reset_stale_transcription_job(
        db_session, PAST_SLOT_2["id"], "testuser", now=reset_time
    )
    assert reset["status"] == "pending"
    assert reset["resetCount"] == 1
    assert "claimToken" not in reset


@pytest.mark.asyncio
async def test_watcher_route_not_found_and_queue_conflict_responses(
    db_client: AsyncClient, db_session: AsyncSession
):
    admin = _headers(is_admin=True)
    missing_claim = await db_client.post(
        "/api/postproduction/missing/transcribe-claim",
        json={"workerId": "watcher-one"},
        headers=admin,
    )
    missing_status = await db_client.put(
        "/api/postproduction/missing/transcribe-status",
        json={"status": "done", "claimToken": "owned"},
        headers=admin,
    )
    missing_reset = await db_client.post(
        "/api/postproduction/missing/transcribe-reset", headers=admin
    )
    assert missing_claim.status_code == 404
    assert missing_status.status_code == 404
    assert missing_reset.status_code == 404

    await db_client.put(
        "/api/data/showSlots", json=[PAST_SLOT_1], headers=_headers()
    )
    await set_production_file_key(db_session, PAST_SLOT_1["id"], "EP001_Test")
    await queue_transcription_job(db_session, PAST_SLOT_1["id"])
    claim = await claim_transcription_job(
        db_session, PAST_SLOT_1["id"], "watcher-one"
    )
    queue_conflict = await db_client.post(
        f"/api/postproduction/{PAST_SLOT_1['id']}/transcribe", headers=_headers()
    )
    heartbeat = await db_client.put(
        f"/api/postproduction/{PAST_SLOT_1['id']}/transcribe-status",
        json={"status": "in_progress", "claimToken": claim["claimToken"]},
        headers=admin,
    )
    assert queue_conflict.status_code == 409
    assert heartbeat.status_code == 200


@pytest.mark.asyncio
async def test_transcription_route_error_mapping_is_explicit(monkeypatch):
    async def empty_queue(_db):
        return []

    monkeypatch.setattr(postproduction_routes, "get_postproduction_queue", empty_queue)
    with pytest.raises(HTTPException) as missing:
        await postproduction_routes.request_transcription("missing", {}, object())
    assert missing.value.status_code == 404

    async def keyless_queue(_db):
        return [{"slotId": "slot", "productionFileKey": None}]

    monkeypatch.setattr(postproduction_routes, "get_postproduction_queue", keyless_queue)
    with pytest.raises(HTTPException) as keyless:
        await postproduction_routes.request_transcription("slot", {}, object())
    assert keyless.value.status_code == 400

    async def usable_queue(_db):
        return [{"slotId": "slot", "productionFileKey": "EP001_Test"}]

    async def conflict(*_args, **_kwargs):
        raise TranscriptionJobConflictError("conflict")

    monkeypatch.setattr(postproduction_routes, "get_postproduction_queue", usable_queue)
    monkeypatch.setattr(postproduction_routes, "queue_transcription_job", conflict)
    with pytest.raises(HTTPException) as queue_conflict:
        await postproduction_routes.request_transcription("slot", {}, object())
    assert queue_conflict.value.status_code == 409

    async def not_found(*_args, **_kwargs):
        raise TranscriptionJobNotFoundError("missing")

    monkeypatch.setattr(postproduction_routes, "claim_transcription_job", not_found)
    with pytest.raises(HTTPException) as claim_missing:
        await postproduction_routes.claim_transcription(
            "missing",
            postproduction_routes.TranscriptionClaimRequest(workerId="watcher"),
            {"is_admin": True},
            object(),
        )
    assert claim_missing.value.status_code == 404
    monkeypatch.setattr(postproduction_routes, "claim_transcription_job", conflict)
    with pytest.raises(HTTPException) as claim_conflict:
        await postproduction_routes.claim_transcription(
            "slot",
            postproduction_routes.TranscriptionClaimRequest(workerId="watcher"),
            {"is_admin": True},
            object(),
        )
    assert claim_conflict.value.status_code == 409

    invalid_status = postproduction_routes.TranscriptionStatusRequest(
        status="invalid", claimToken="owned"
    )
    with pytest.raises(HTTPException) as invalid:
        await postproduction_routes.update_transcription_status(
            "slot", invalid_status, {"is_admin": True}, object()
        )
    assert invalid.value.status_code == 400
    valid_status = postproduction_routes.TranscriptionStatusRequest(
        status="done", claimToken="owned"
    )
    monkeypatch.setattr(postproduction_routes, "update_transcription_claim", not_found)
    with pytest.raises(HTTPException) as status_missing:
        await postproduction_routes.update_transcription_status(
            "missing", valid_status, {"is_admin": True}, object()
        )
    assert status_missing.value.status_code == 404
    monkeypatch.setattr(postproduction_routes, "update_transcription_claim", conflict)
    with pytest.raises(HTTPException) as status_conflict:
        await postproduction_routes.update_transcription_status(
            "slot", valid_status, {"is_admin": True}, object()
        )
    assert status_conflict.value.status_code == 409

    monkeypatch.setattr(postproduction_routes, "reset_stale_transcription_job", not_found)
    with pytest.raises(HTTPException) as reset_missing:
        await postproduction_routes.reset_transcription(
            "missing", {"is_admin": True, "username": "admin"}, object()
        )
    assert reset_missing.value.status_code == 404
    monkeypatch.setattr(postproduction_routes, "reset_stale_transcription_job", conflict)
    with pytest.raises(HTTPException) as reset_conflict:
        await postproduction_routes.reset_transcription(
            "slot", {"is_admin": True, "username": "admin"}, object()
        )
    assert reset_conflict.value.status_code == 409
