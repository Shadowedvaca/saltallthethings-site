"""Database/API coverage for per-show episode-number overrides."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient

from satt.config import get_settings


def _headers() -> dict:
    settings = get_settings()
    token = jwt.encode(
        {
            "user_id": 1,
            "username": "testuser",
            "is_admin": False,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc),
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


def _idea(identifier: str, title: str) -> dict:
    return {
        "id": identifier,
        "titles": [title],
        "selectedTitle": title,
        "summary": f"Summary for {title}",
        "outline": [],
        "status": "processed",
        "imageFileId": None,
        "rawNotes": None,
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
    }


def _slot(identifier: str, number: int) -> dict:
    return {
        "id": identifier,
        "episodeNumber": f"EP{number:03d}",
        "episodeNum": number,
        "episodeNumberOverride": None,
        "recordDate": f"2026-01-{number:02d}",
        "releaseDate": f"2026-01-{number + 7:02d}",
        "isRollout": False,
        "releaseDateOverride": None,
    }


async def _seed(
    client: AsyncClient,
    *,
    assignments: dict[str, str],
) -> None:
    response = await client.put(
        "/api/data/ideas",
        json=[_idea("idea-1", "First"), _idea("idea-2", "Second")],
        headers=_headers(),
    )
    assert response.status_code == 200
    response = await client.put(
        "/api/data/showSlots",
        json=[_slot("slot-1", 1), _slot("slot-2", 2)],
        headers=_headers(),
    )
    assert response.status_code == 200
    response = await client.put(
        "/api/data/assignments", json=assignments, headers=_headers()
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_override_round_trip_public_output_and_reset_preserve_schedule(
    db_client: AsyncClient,
):
    await _seed(db_client, assignments={"slot-2": "idea-2"})
    before = (await db_client.get("/api/export", headers=_headers())).json()

    saved = await db_client.put(
        "/api/schedule/slot-2/episode-number",
        json={"episodeNumber": 1},
        headers=_headers(),
    )
    assert saved.status_code == 200
    state = saved.json()["state"]
    slot = next(item for item in state["showSlots"] if item["id"] == "slot-2")
    assert slot["episodeNumber"] == "EP002"
    assert slot["episodeNum"] == 2
    assert slot["episodeNumberOverride"] == 1
    assert slot["effectiveEpisodeNumber"] == "EP001"
    assert state["assignments"] == before["assignments"]
    assert slot["recordDate"] == "2026-01-02"
    assert slot["releaseDate"] == "2026-01-09"

    reloaded = (await db_client.get("/api/export", headers=_headers())).json()
    reloaded_slot = next(
        item for item in reloaded["showSlots"] if item["id"] == "slot-2"
    )
    assert reloaded_slot == slot
    public = await db_client.get("/public/episodes")
    assert public.status_code == 200
    assert public.json()["episodes"][0]["episodeNumber"] == "EP001"
    postproduction = await db_client.get("/api/postproduction", headers=_headers())
    assert postproduction.status_code == 200
    postproduction_slot = next(
        item for item in postproduction.json() if item["slotId"] == "slot-2"
    )
    assert postproduction_slot["episodeNumber"] == "EP001"

    reset = await db_client.delete(
        "/api/schedule/slot-2/episode-number", headers=_headers()
    )
    assert reset.status_code == 200
    reset_state = reset.json()["state"]
    reset_slot = next(
        item for item in reset_state["showSlots"] if item["id"] == "slot-2"
    )
    assert reset_slot["episodeNumberOverride"] is None
    assert reset_slot["effectiveEpisodeNumber"] == "EP002"
    assert reset_state["assignments"] == before["assignments"]


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [None, True, False, "3", 0, -1, 2_147_483_648])
async def test_override_endpoint_rejects_invalid_values(
    db_client: AsyncClient,
    invalid,
):
    await _seed(db_client, assignments={"slot-2": "idea-2"})
    response = await db_client.put(
        "/api/schedule/slot-2/episode-number",
        json={"episodeNumber": invalid},
        headers=_headers(),
    )
    assert response.status_code == 422
    slot = (await db_client.get("/api/data/showSlots", headers=_headers())).json()[1]
    assert slot["episodeNumberOverride"] is None
    assert slot["effectiveEpisodeNumber"] == "EP002"


@pytest.mark.asyncio
async def test_conflicting_effective_numbers_are_rejected_without_partial_save(
    db_client: AsyncClient,
):
    await _seed(
        db_client,
        assignments={"slot-1": "idea-1", "slot-2": "idea-2"},
    )
    first = await db_client.put(
        "/api/schedule/slot-2/episode-number",
        json={"episodeNumber": 3},
        headers=_headers(),
    )
    assert first.status_code == 200

    conflict = await db_client.put(
        "/api/schedule/slot-1/episode-number",
        json={"episodeNumber": 3},
        headers=_headers(),
    )
    assert conflict.status_code == 422
    assert "already used by another scheduled show" in conflict.json()["detail"]
    state = (await db_client.get("/api/export", headers=_headers())).json()
    slots = {slot["id"]: slot for slot in state["showSlots"]}
    assert slots["slot-1"]["episodeNumberOverride"] is None
    assert slots["slot-1"]["effectiveEpisodeNumber"] == "EP001"
    assert slots["slot-2"]["effectiveEpisodeNumber"] == "EP003"
    assert state["assignments"] == {"slot-1": "idea-1", "slot-2": "idea-2"}


@pytest.mark.asyncio
async def test_assignment_cannot_activate_a_duplicate_effective_number(
    db_client: AsyncClient,
):
    await _seed(db_client, assignments={"slot-2": "idea-2"})
    override = await db_client.put(
        "/api/schedule/slot-2/episode-number",
        json={"episodeNumber": 1},
        headers=_headers(),
    )
    assert override.status_code == 200

    conflict = await db_client.put(
        "/api/schedule/slot-1/assignment",
        json={"ideaId": "idea-1"},
        headers=_headers(),
    )
    assert conflict.status_code == 422
    state = (await db_client.get("/api/export", headers=_headers())).json()
    assert state["assignments"] == {"slot-2": "idea-2"}
    assert next(
        idea for idea in state["ideas"] if idea["id"] == "idea-1"
    )["status"] == "processed"


@pytest.mark.asyncio
async def test_override_routes_reject_missing_slots_and_invalid_full_writes(
    db_client: AsyncClient,
):
    missing_put = await db_client.put(
        "/api/schedule/missing/episode-number",
        json={"episodeNumber": 7},
        headers=_headers(),
    )
    assert missing_put.status_code == 404
    missing_delete = await db_client.delete(
        "/api/schedule/missing/episode-number", headers=_headers()
    )
    assert missing_delete.status_code == 404

    invalid_slots = await db_client.put(
        "/api/data/showSlots",
        json=[{**_slot("slot-1", 1), "episodeNumberOverride": "7"}],
        headers=_headers(),
    )
    assert invalid_slots.status_code == 422
    assert "positive whole number" in invalid_slots.json()["detail"]

    invalid_import = await db_client.put(
        "/api/import",
        json={
            "showSlots": [
                {**_slot("slot-1", 1), "episodeNumberOverride": 0}
            ]
        },
        headers=_headers(),
    )
    assert invalid_import.status_code == 422
    assert "between 1 and 2147483647" in invalid_import.json()["detail"]
