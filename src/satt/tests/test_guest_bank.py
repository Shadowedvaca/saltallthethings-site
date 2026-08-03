"""Guest Bank API, persistence, statistics, lifecycle, and privacy coverage."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from satt.config import get_settings
from satt.guest_crud import assign_guest_to_idea
from satt.models import Guest, GuestAssignment, Idea


def _headers(**extra: str) -> dict[str, str]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "user_id": 1,
            "username": "guest-test",
            "is_admin": False,
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}", **extra}


def _idea(idea_id: str, title: str | None = None) -> dict:
    return {
        "id": idea_id,
        "titles": [title or idea_id],
        "selectedTitle": title or idea_id,
        "summary": "Guest test idea",
        "outline": [],
        "status": "processed",
    }


def _guest(guest_id: str, name: str = "Guest One", **updates) -> dict:
    return {
        "id": guest_id,
        "displayName": name,
        "privateNotes": "host-only guest notes",
        "status": "active",
        "createdAt": "2026-08-03T00:00:00Z",
        **updates,
    }


def _slot(slot_id: str, episode: int, release_date: str, override: str | None = None):
    return {
        "id": slot_id,
        "episodeNumber": str(episode),
        "episodeNum": episode,
        "recordDate": release_date,
        "releaseDate": release_date,
        "releaseDateOverride": override,
        "isRollout": False,
    }


@pytest.mark.asyncio
async def test_guest_round_trip_and_authenticated_export_use_camelcase(
    db_client: AsyncClient,
):
    saved = await db_client.put(
        "/api/data/guests", json=[_guest("guest-round-trip")], headers=_headers()
    )
    assert saved.status_code == 200
    [guest] = saved.json()["data"]
    assert set(guest) == {
        "id",
        "displayName",
        "privateNotes",
        "status",
        "createdAt",
        "updatedAt",
        "totalAppearances",
        "firstAppearance",
        "mostRecentAppearance",
        "appearanceHistory",
    }
    assert guest["displayName"] == "Guest One"
    assert guest["totalAppearances"] == 0
    assert guest["firstAppearance"] is None
    assert guest["mostRecentAppearance"] is None

    reloaded = await db_client.get("/api/data/guests", headers=_headers())
    assert reloaded.json() == [guest]
    exported = await db_client.get("/api/export", headers=_headers())
    assert exported.json()["guests"] == [guest]
    assert exported.json()["guestAssignments"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload,detail",
    [
        ([_guest("bad id")], "opaque ID"),
        ([_guest("guest-empty", name=" ")], "displayName"),
        ([_guest("guest-state", status="retired")], "status"),
        ([_guest("guest-dup"), _guest("guest-dup")], "duplicates"),
    ],
)
async def test_guest_writes_reject_invalid_contract(
    db_client: AsyncClient, payload: list[dict], detail: str
):
    response = await db_client.put("/api/data/guests", json=payload, headers=_headers())
    assert response.status_code == 422
    assert detail in response.json()["detail"]


@pytest.mark.asyncio
async def test_guest_routes_require_authentication(client: AsyncClient):
    assert (await client.get("/api/data/guests")).status_code == 401
    assert (await client.get("/api/data/guestAssignments")).status_code == 401
    assert (await client.put("/api/guests/guest/assignments/idea")).status_code == 401


@pytest.mark.asyncio
async def test_many_to_many_assignment_is_reusable_idempotent_and_persistent(
    db_client: AsyncClient,
):
    await db_client.put(
        "/api/data/ideas",
        json=[_idea("guest-idea-one"), _idea("guest-idea-two")],
        headers=_headers(),
    )
    await db_client.put(
        "/api/data/guests",
        json=[_guest("guest-one"), _guest("guest-two", "Guest Two")],
        headers=_headers(),
    )
    for guest_id, idea_id in (
        ("guest-one", "guest-idea-one"),
        ("guest-one", "guest-idea-two"),
        ("guest-two", "guest-idea-one"),
    ):
        response = await db_client.put(
            f"/api/guests/{guest_id}/assignments/{idea_id}", headers=_headers()
        )
        assert response.status_code == 200

    before = await db_client.get("/api/export", headers=_headers())
    revision = before.json()["revision"]
    repeated = await db_client.put(
        "/api/guests/guest-one/assignments/guest-idea-one",
        headers=_headers(**{"If-Match": str(revision)}),
    )
    assert repeated.status_code == 200
    assert repeated.json()["revision"] == revision

    assignments = repeated.json()["state"]["guestAssignments"]
    assert {(item["guestId"], item["ideaId"]) for item in assignments} == {
        ("guest-one", "guest-idea-one"),
        ("guest-one", "guest-idea-two"),
        ("guest-two", "guest-idea-one"),
    }
    guests = {guest["id"]: guest for guest in repeated.json()["state"]["guests"]}
    assert guests["guest-one"]["totalAppearances"] == 2
    assert guests["guest-two"]["totalAppearances"] == 1


@pytest.mark.asyncio
async def test_statistics_use_only_effective_scheduled_dates_and_reschedule(
    db_client: AsyncClient,
):
    await db_client.put(
        "/api/data/ideas",
        json=[
            _idea("appearance-early", "Early"),
            _idea("appearance-late", "Late"),
            _idea("appearance-unscheduled", "Unscheduled"),
        ],
        headers=_headers(),
    )
    await db_client.put(
        "/api/data/guests", json=[_guest("appearance-guest")], headers=_headers()
    )
    for idea_id in (
        "appearance-early",
        "appearance-late",
        "appearance-unscheduled",
    ):
        await db_client.put(
            f"/api/guests/appearance-guest/assignments/{idea_id}",
            headers=_headers(),
        )
    await db_client.put(
        "/api/data/showSlots",
        json=[
            _slot("slot-early", 10, "2026-08-10"),
            _slot("slot-late", 20, "2026-08-20", "2026-08-25"),
        ],
        headers=_headers(),
    )
    await db_client.put(
        "/api/schedule/slot-early/assignment",
        json={"ideaId": "appearance-early"},
        headers=_headers(),
    )
    await db_client.put(
        "/api/schedule/slot-late/assignment",
        json={"ideaId": "appearance-late"},
        headers=_headers(),
    )

    [guest] = (await db_client.get("/api/data/guests", headers=_headers())).json()
    assert guest["totalAppearances"] == 3
    assert guest["firstAppearance"] == "2026-08-10"
    assert guest["mostRecentAppearance"] == "2026-08-25"
    by_idea = {item["ideaId"]: item for item in guest["appearanceHistory"]}
    assert by_idea["appearance-unscheduled"] == {
        "ideaId": "appearance-unscheduled",
        "title": "Unscheduled",
        "slotId": None,
        "episodeNumber": None,
        "releaseDate": None,
        "scheduled": False,
    }

    await db_client.put(
        "/api/data/showSlots",
        json=[
            _slot("slot-early", 10, "2026-09-10"),
            _slot("slot-late", 20, "2026-08-20", "2026-08-22"),
        ],
        headers=_headers(),
    )
    [rescheduled] = (await db_client.get("/api/data/guests", headers=_headers())).json()
    assert rescheduled["totalAppearances"] == 3
    assert rescheduled["firstAppearance"] == "2026-08-22"
    assert rescheduled["mostRecentAppearance"] == "2026-09-10"


@pytest.mark.asyncio
async def test_only_unscheduled_appearance_has_explicit_null_dates(
    db_client: AsyncClient,
):
    await db_client.put(
        "/api/data/ideas", json=[_idea("only-unscheduled")], headers=_headers()
    )
    await db_client.put(
        "/api/data/guests", json=[_guest("only-unscheduled-guest")], headers=_headers()
    )
    await db_client.put(
        "/api/guests/only-unscheduled-guest/assignments/only-unscheduled",
        headers=_headers(),
    )
    [guest] = (await db_client.get("/api/data/guests", headers=_headers())).json()
    assert guest["totalAppearances"] == 1
    assert guest["firstAppearance"] is None
    assert guest["mostRecentAppearance"] is None
    assert guest["appearanceHistory"][0]["scheduled"] is False


@pytest.mark.asyncio
async def test_archive_restore_unassign_and_protected_delete_lifecycle(
    db_client: AsyncClient,
):
    await db_client.put(
        "/api/data/ideas",
        json=[_idea("archive-existing"), _idea("archive-new")],
        headers=_headers(),
    )
    await db_client.put(
        "/api/data/guests", json=[_guest("archive-guest")], headers=_headers()
    )
    await db_client.put(
        "/api/guests/archive-guest/assignments/archive-existing",
        headers=_headers(),
    )
    archived = await db_client.put(
        "/api/guests/archive-guest/status",
        json={"status": "archived"},
        headers=_headers(),
    )
    assert archived.status_code == 200
    assert archived.json()["data"][0]["totalAppearances"] == 1

    rejected = await db_client.put(
        "/api/guests/archive-guest/assignments/archive-new", headers=_headers()
    )
    assert rejected.status_code == 409
    assert "Archived" in rejected.json()["detail"]
    protected = await db_client.delete("/api/guests/archive-guest", headers=_headers())
    assert protected.status_code == 409
    assert "remove every show assignment" in protected.json()["detail"]

    restored = await db_client.put(
        "/api/guests/archive-guest/status",
        json={"status": "active"},
        headers=_headers(),
    )
    assert restored.status_code == 200
    assigned = await db_client.put(
        "/api/guests/archive-guest/assignments/archive-new", headers=_headers()
    )
    assert assigned.status_code == 200
    for idea_id in ("archive-existing", "archive-new"):
        removed = await db_client.delete(
            f"/api/guests/archive-guest/assignments/{idea_id}", headers=_headers()
        )
        assert removed.status_code == 200
    repeated = await db_client.delete(
        "/api/guests/archive-guest/assignments/archive-new", headers=_headers()
    )
    assert repeated.status_code == 200
    deleted = await db_client.delete("/api/guests/archive-guest", headers=_headers())
    assert deleted.status_code == 200
    assert deleted.json()["data"] == []


@pytest.mark.asyncio
async def test_idea_deletion_cascades_links_without_deleting_guest(
    db_client: AsyncClient,
):
    await db_client.put(
        "/api/data/ideas", json=[_idea("guest-deleted-idea")], headers=_headers()
    )
    await db_client.put(
        "/api/data/guests", json=[_guest("preserved-guest")], headers=_headers()
    )
    await db_client.put(
        "/api/guests/preserved-guest/assignments/guest-deleted-idea",
        headers=_headers(),
    )
    deleted = await db_client.delete(
        "/api/ideas/guest-deleted-idea", headers=_headers()
    )
    assert deleted.status_code == 200
    assert deleted.json()["data"]["guestAssignments"] == []
    [guest] = deleted.json()["data"]["guests"]
    assert guest["id"] == "preserved-guest"
    assert guest["totalAppearances"] == 0


@pytest.mark.asyncio
async def test_import_compatibility_and_reference_validation(db_client: AsyncClient):
    await db_client.put(
        "/api/data/ideas", json=[_idea("import-guest-idea")], headers=_headers()
    )
    await db_client.put(
        "/api/data/guests", json=[_guest("import-guest")], headers=_headers()
    )
    legacy = await db_client.put(
        "/api/import",
        json={"config": {"youtubeVideo1": "legacy-guest-backup"}},
        headers=_headers(),
    )
    assert legacy.status_code == 200
    assert [guest["id"] for guest in legacy.json()["state"]["guests"]] == [
        "import-guest"
    ]

    missing_guest = await db_client.put(
        "/api/data/guestAssignments",
        json=[{"guestId": "missing", "ideaId": "import-guest-idea"}],
        headers=_headers(),
    )
    assert missing_guest.status_code == 422
    assert "existing guest" in missing_guest.json()["detail"]
    missing_idea = await db_client.put(
        "/api/data/guestAssignments",
        json=[{"guestId": "import-guest", "ideaId": "missing"}],
        headers=_headers(),
    )
    assert missing_idea.status_code == 422
    assert "existing idea" in missing_idea.json()["detail"]
    duplicate = await db_client.put(
        "/api/data/guestAssignments",
        json=[
            {"guestId": "import-guest", "ideaId": "import-guest-idea"},
            {"guestId": "import-guest", "ideaId": "import-guest-idea"},
        ],
        headers=_headers(),
    )
    assert duplicate.status_code == 422
    assert "duplicates" in duplicate.json()["detail"]


@pytest.mark.asyncio
async def test_full_export_import_preserves_archived_guest_assignment(
    db_client: AsyncClient,
):
    await db_client.put(
        "/api/data/ideas", json=[_idea("archived-import-idea")], headers=_headers()
    )
    await db_client.put(
        "/api/data/guests",
        json=[_guest("archived-import-guest")],
        headers=_headers(),
    )
    await db_client.put(
        "/api/guests/archived-import-guest/assignments/archived-import-idea",
        headers=_headers(),
    )
    await db_client.put(
        "/api/guests/archived-import-guest/status",
        json={"status": "archived"},
        headers=_headers(),
    )
    exported = (await db_client.get("/api/export", headers=_headers())).json()
    payload = {key: value for key, value in exported.items() if key != "revision"}
    imported = await db_client.put("/api/import", json=payload, headers=_headers())
    assert imported.status_code == 200
    [guest] = imported.json()["state"]["guests"]
    assert guest["status"] == "archived"
    assert guest["totalAppearances"] == 1
    assert imported.json()["state"]["guestAssignments"][0]["ideaId"] == (
        "archived-import-idea"
    )


@pytest.mark.asyncio
async def test_stale_guest_write_cannot_replace_newer_data(db_client: AsyncClient):
    revision = (await db_client.get("/api/export", headers=_headers())).json()[
        "revision"
    ]
    fresh = await db_client.put(
        "/api/data/guests",
        json=[_guest("fresh-guest")],
        headers=_headers(**{"If-Match": str(revision)}),
    )
    stale = await db_client.put(
        "/api/data/guests",
        json=[_guest("stale-guest")],
        headers=_headers(**{"If-Match": str(revision)}),
    )
    assert fresh.status_code == 200
    assert stale.status_code == 409
    assert [
        guest["id"]
        for guest in (
            await db_client.get("/api/data/guests", headers=_headers())
        ).json()
    ] == ["fresh-guest"]


@pytest.mark.asyncio
async def test_database_primary_key_rejects_duplicate_guest_idea_pair(
    db_session: AsyncSession,
):
    db_session.add(Guest(id="constraint-guest", display_name="Constraint"))
    db_session.add(Idea(id="constraint-idea"))
    db_session.add_all(
        [
            GuestAssignment(guest_id="constraint-guest", idea_id="constraint-idea"),
            GuestAssignment(guest_id="constraint-guest", idea_id="constraint-idea"),
        ]
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_concurrent_assignment_requests_create_one_link_and_count(
    db_session: AsyncSession,
):
    guest_id = "concurrent-guest"
    idea_id = "concurrent-idea"
    db_session.add(Guest(id=guest_id, display_name="Concurrent"))
    db_session.add(Idea(id=idea_id))
    await db_session.commit()
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def assign() -> None:
        async with factory() as session:
            await assign_guest_to_idea(session, guest_id, idea_id)
            await session.commit()

    try:
        await asyncio.gather(assign(), assign())
        async with factory() as verify:
            count = await verify.scalar(
                select(func.count())
                .select_from(GuestAssignment)
                .where(
                    GuestAssignment.guest_id == guest_id,
                    GuestAssignment.idea_id == idea_id,
                )
            )
            assert count == 1
    finally:
        async with factory() as cleanup:
            await cleanup.execute(
                delete(GuestAssignment).where(GuestAssignment.guest_id == guest_id)
            )
            await cleanup.execute(delete(Guest).where(Guest.id == guest_id))
            await cleanup.execute(delete(Idea).where(Idea.id == idea_id))
            await cleanup.commit()


@pytest.mark.asyncio
async def test_guest_private_data_never_appears_in_public_routes(
    db_client: AsyncClient,
):
    sentinel_name = "PRIVATE-GUEST-NAME-SENTINEL"
    sentinel_notes = "PRIVATE-GUEST-NOTES-SENTINEL"
    await db_client.put(
        "/api/data/ideas", json=[_idea("privacy-guest-idea")], headers=_headers()
    )
    await db_client.put(
        "/api/data/guests",
        json=[
            _guest(
                "privacy-guest",
                sentinel_name,
                privateNotes=sentinel_notes,
            )
        ],
        headers=_headers(),
    )
    await db_client.put(
        "/api/guests/privacy-guest/assignments/privacy-guest-idea",
        headers=_headers(),
    )
    for path in ("/public/episodes", "/public/homepage"):
        response = await db_client.get(path)
        assert response.status_code == 200
        assert sentinel_name not in response.text
        assert sentinel_notes not in response.text
