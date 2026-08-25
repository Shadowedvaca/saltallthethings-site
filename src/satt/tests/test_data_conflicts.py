"""Conflict, atomicity, and schedule integrity tests for issue #10."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from satt.config import get_settings
from satt.main import app


def _token() -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "user_id": 1,
            "username": "conflict-test",
            "is_admin": False,
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def _headers(**extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", **extra}


def _idea(idea_id: str, status: str = "processed") -> dict:
    return {
        "id": idea_id,
        "titles": [idea_id],
        "selectedTitle": idea_id,
        "summary": "Conflict-safe idea",
        "outline": [],
        "status": status,
        "createdAt": "2026-07-29T00:00:00Z",
        "updatedAt": "2026-07-29T00:00:00Z",
    }


def _slot(slot_id: str, episode: int) -> dict:
    return {
        "id": slot_id,
        "episodeNumber": f"EP{episode}",
        "episodeNum": episode,
        "recordDate": "2026-08-01",
        "releaseDate": "2026-08-08",
        "isRollout": False,
        "releaseDateOverride": None,
    }


@pytest.mark.asyncio
async def test_mutation_requires_if_match(db_client: AsyncClient):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as raw_client:
        response = await raw_client.put(
            "/api/data/config",
            json={"aiModel": "claude"},
            headers=_headers(),
        )
    assert response.status_code == 428
    assert "If-Match" in response.json()["detail"]


@pytest.mark.asyncio
async def test_stale_client_cannot_overwrite_newer_server_data(
    db_client: AsyncClient,
):
    initial = await db_client.get("/api/export", headers=_headers())
    revision = initial.json()["revision"]

    first = await db_client.put(
        "/api/data/config",
        json={"youtubeVideo1": "newer-value"},
        headers=_headers(**{"If-Match": str(revision)}),
    )
    assert first.status_code == 200
    assert first.json()["revision"] > revision

    stale = await db_client.put(
        "/api/data/ideas",
        json=[_idea("stale-overwrite")],
        headers=_headers(**{"If-Match": str(revision)}),
    )
    assert stale.status_code == 409
    detail = stale.json()["detail"]
    assert detail["currentRevision"] == first.json()["revision"]

    current = await db_client.get("/api/export", headers=_headers())
    assert current.json()["config"]["youtubeVideo1"] == "newer-value"
    assert current.json()["ideas"] == []


@pytest.mark.asyncio
async def test_schedule_mutations_update_assignments_and_statuses_atomically(
    db_client: AsyncClient,
):
    await db_client.put(
        "/api/data/ideas",
        json=[_idea("idea-1"), _idea("idea-2")],
        headers=_headers(),
    )
    await db_client.put(
        "/api/data/showSlots",
        json=[_slot("slot-1", 1), _slot("slot-2", 2)],
        headers=_headers(),
    )

    assigned = await db_client.put(
        "/api/schedule/slot-1/assignment",
        json={"ideaId": "idea-1"},
        headers=_headers(),
    )
    assert assigned.status_code == 200
    assert assigned.json()["state"]["assignments"] == {"slot-1": "idea-1"}

    replaced = await db_client.put(
        "/api/schedule/slot-1/assignment",
        json={"ideaId": "idea-2"},
        headers=_headers(),
    )
    state = replaced.json()["state"]
    assert state["assignments"] == {"slot-1": "idea-2"}
    statuses = {idea["id"]: idea["status"] for idea in state["ideas"]}
    assert statuses == {"idea-1": "processed", "idea-2": "scheduled"}

    moved = await db_client.put(
        "/api/schedule/slot-2/assignment",
        json={"ideaId": "idea-2"},
        headers=_headers(),
    )
    assert moved.json()["state"]["assignments"] == {"slot-2": "idea-2"}

    removed = await db_client.delete(
        "/api/schedule/slot-2/assignment", headers=_headers()
    )
    state = removed.json()["state"]
    assert state["assignments"] == {}
    assert {idea["id"]: idea["status"] for idea in state["ideas"]} == {
        "idea-1": "processed",
        "idea-2": "processed",
    }


@pytest.mark.asyncio
async def test_editing_scheduled_idea_preserves_assignment_and_slot_dates(
    db_client: AsyncClient,
):
    await db_client.put(
        "/api/data/ideas",
        json=[_idea("scheduled-edit")],
        headers=_headers(),
    )
    slot = _slot("scheduled-edit-slot", 41)
    await db_client.put(
        "/api/data/showSlots",
        json=[slot],
        headers=_headers(),
    )
    assigned = await db_client.put(
        "/api/schedule/scheduled-edit-slot/assignment",
        json={"ideaId": "scheduled-edit"},
        headers=_headers(),
    )
    assigned_state = assigned.json()["state"]
    scheduled_idea = assigned_state["ideas"][0]
    assert scheduled_idea["status"] == "scheduled"

    scheduled_idea["summary"] = "Edited while the show remains scheduled"
    edited = await db_client.put(
        "/api/data/ideas",
        json=[scheduled_idea],
        headers=_headers(),
    )
    state = edited.json()["state"]

    assert state["assignments"] == {"scheduled-edit-slot": "scheduled-edit"}
    assert state["showSlots"] == [slot]
    assert state["ideas"][0]["status"] == "scheduled"
    assert state["ideas"][0]["summary"] == "Edited while the show remains scheduled"

    reloaded = (await db_client.get("/api/export", headers=_headers())).json()
    assert reloaded["assignments"] == state["assignments"]
    assert reloaded["showSlots"] == state["showSlots"]
    assert reloaded["ideas"] == state["ideas"]

@pytest.mark.asyncio
async def test_import_failure_rolls_back_every_entity(db_client: AsyncClient):
    baseline = {
        "config": {"youtubeVideo1": "baseline"},
        "ideas": [_idea("baseline-idea")],
        "showSlots": [_slot("baseline-slot", 10)],
        "assignments": {"baseline-slot": "baseline-idea"},
    }
    assert (
        await db_client.put("/api/import", json=baseline, headers=_headers())
    ).status_code == 200

    invalid = {
        "config": {"youtubeVideo1": "must-roll-back"},
        "ideas": [_idea("replacement")],
        "showSlots": [_slot("slot-a", 11), _slot("slot-b", 12)],
        "assignments": {"slot-a": "replacement", "slot-b": "replacement"},
    }
    failed = await db_client.put("/api/import", json=invalid, headers=_headers())
    assert failed.status_code == 422
    assert "only be assigned to one" in failed.json()["detail"]

    current = (await db_client.get("/api/export", headers=_headers())).json()
    assert current["config"]["youtubeVideo1"] == "baseline"
    assert [idea["id"] for idea in current["ideas"]] == ["baseline-idea"]
    assert [slot["id"] for slot in current["showSlots"]] == ["baseline-slot"]
    assert current["assignments"] == {"baseline-slot": "baseline-idea"}
