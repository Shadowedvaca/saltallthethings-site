"""Authenticated Song Bank API, persistence, lifecycle, and privacy coverage."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from satt.config import get_settings
from satt.models import Idea, Song
from satt.song_crud import assign_song_to_idea


def _headers(**extra: str) -> dict[str, str]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "user_id": 1,
            "username": "song-test",
            "is_admin": False,
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}", **extra}


def _idea(idea_id: str) -> dict:
    return {
        "id": idea_id,
        "titles": [idea_id],
        "selectedTitle": idea_id,
        "summary": "Song test idea",
        "outline": [],
        "status": "processed",
    }


def _song(song_id: str, title: str = "Song") -> dict:
    return {
        "id": song_id,
        "artist": "Test Artist",
        "title": title,
        "youtubeUrl": "https://youtu.be/abcdefghijk",
        "privateNotes": "Keep this in authenticated preparation views.",
        "status": "unused",
        "assignedIdeaId": None,
        "createdAt": "2026-07-31T00:00:00Z",
        "updatedAt": "2026-07-31T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_song_round_trip_uses_camelcase_contract(db_client: AsyncClient):
    response = await db_client.put(
        "/api/data/songs", json=[_song("song-round-trip")], headers=_headers()
    )
    assert response.status_code == 200
    [song] = response.json()["data"]
    assert set(song) == {
        "id",
        "artist",
        "title",
        "youtubeUrl",
        "privateNotes",
        "status",
        "assignedIdeaId",
        "createdAt",
        "updatedAt",
    }
    assert song["privateNotes"].startswith("Keep this")
    assert song["createdAt"].startswith("2026-07-31")
    assert song["updatedAt"] != "2026-07-31T00:00:00+00:00"

    reloaded = await db_client.get("/api/data/songs", headers=_headers())
    assert reloaded.json() == [song]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "updates,detail",
    [
        ({"artist": ""}, "artist"),
        ({"title": ""}, "title"),
        ({"youtubeUrl": "https://example.com/video"}, "youtubeUrl"),
    ],
)
async def test_song_write_rejects_invalid_contract(
    db_client: AsyncClient, updates: dict, detail: str
):
    response = await db_client.put(
        "/api/data/songs",
        json=[{**_song("invalid-song"), **updates}],
        headers=_headers(),
    )
    assert response.status_code == 422
    assert detail in response.json()["detail"]


@pytest.mark.asyncio
async def test_song_routes_require_authentication(client: AsyncClient):
    assert (await client.get("/api/data/songs")).status_code == 401
    assert (
        await client.put(
            "/api/songs/missing/assignment", json={"ideaId": "idea"}
        )
    ).status_code == 401


@pytest.mark.asyncio
async def test_assignment_replacement_move_and_free_survive_reload(
    db_client: AsyncClient,
):
    await db_client.put(
        "/api/data/ideas",
        json=[_idea("song-idea-one"), _idea("song-idea-two")],
        headers=_headers(),
    )
    await db_client.put(
        "/api/data/songs",
        json=[_song("song-one", "One"), _song("song-two", "Two")],
        headers=_headers(),
    )

    first = await db_client.put(
        "/api/songs/song-one/assignment",
        json={"ideaId": "song-idea-one"},
        headers=_headers(),
    )
    assert first.status_code == 200
    replaced = await db_client.put(
        "/api/songs/song-two/assignment",
        json={"ideaId": "song-idea-one"},
        headers=_headers(),
    )
    assert replaced.status_code == 200
    moved = await db_client.put(
        "/api/songs/song-two/assignment",
        json={"ideaId": "song-idea-two"},
        headers=_headers(),
    )
    assert moved.status_code == 200

    reloaded = await db_client.get("/api/data/songs", headers=_headers())
    by_id = {song["id"]: song for song in reloaded.json()}
    assert by_id["song-one"]["status"] == "unused"
    assert by_id["song-one"]["assignedIdeaId"] is None
    assert by_id["song-two"]["status"] == "used"
    assert by_id["song-two"]["assignedIdeaId"] == "song-idea-two"

    freed = await db_client.delete(
        "/api/songs/song-two/assignment", headers=_headers()
    )
    [song_two] = [song for song in freed.json()["data"] if song["id"] == "song-two"]
    assert song_two["status"] == "unused"
    assert song_two["assignedIdeaId"] is None


@pytest.mark.asyncio
async def test_assignment_routes_reject_missing_records_without_mutation(
    db_client: AsyncClient,
):
    await db_client.put(
        "/api/data/ideas", json=[_idea("existing-song-idea")], headers=_headers()
    )
    await db_client.put(
        "/api/data/songs", json=[_song("existing-song")], headers=_headers()
    )

    missing_song = await db_client.put(
        "/api/songs/missing-song/assignment",
        json={"ideaId": "existing-song-idea"},
        headers=_headers(),
    )
    missing_idea = await db_client.put(
        "/api/songs/existing-song/assignment",
        json={"ideaId": "missing-song-idea"},
        headers=_headers(),
    )

    assert missing_song.status_code == 404
    assert "Song not found" in missing_song.json()["detail"]
    assert missing_idea.status_code == 404
    assert "Idea not found" in missing_idea.json()["detail"]
    [song] = (await db_client.get("/api/data/songs", headers=_headers())).json()
    assert song["status"] == "unused"
    assert song["assignedIdeaId"] is None


@pytest.mark.asyncio
async def test_stale_assignment_cannot_replace_newer_episode_song(
    db_client: AsyncClient,
):
    await db_client.put(
        "/api/data/ideas", json=[_idea("stale-assignment-idea")], headers=_headers()
    )
    await db_client.put(
        "/api/data/songs",
        json=[_song("fresh-assignment-song"), _song("stale-assignment-song")],
        headers=_headers(),
    )
    revision = (await db_client.get("/api/export", headers=_headers())).json()[
        "revision"
    ]

    fresh = await db_client.put(
        "/api/songs/fresh-assignment-song/assignment",
        json={"ideaId": "stale-assignment-idea"},
        headers=_headers(**{"If-Match": str(revision)}),
    )
    stale = await db_client.put(
        "/api/songs/stale-assignment-song/assignment",
        json={"ideaId": "stale-assignment-idea"},
        headers=_headers(**{"If-Match": str(revision)}),
    )

    assert fresh.status_code == 200
    assert stale.status_code == 409
    songs = (await db_client.get("/api/data/songs", headers=_headers())).json()
    assigned = [song for song in songs if song["assignedIdeaId"]]
    assert [song["id"] for song in assigned] == ["fresh-assignment-song"]


@pytest.mark.asyncio
async def test_retire_frees_assignment_and_retired_song_cannot_be_assigned(
    db_client: AsyncClient,
):
    await db_client.put(
        "/api/data/ideas", json=[_idea("retire-idea")], headers=_headers()
    )
    await db_client.put(
        "/api/data/songs", json=[_song("retire-song")], headers=_headers()
    )
    await db_client.put(
        "/api/songs/retire-song/assignment",
        json={"ideaId": "retire-idea"},
        headers=_headers(),
    )
    retired = await db_client.put(
        "/api/songs/retire-song/status",
        json={"status": "retired"},
        headers=_headers(),
    )
    [song] = retired.json()["data"]
    assert song["status"] == "retired"
    assert song["assignedIdeaId"] is None

    rejected = await db_client.put(
        "/api/songs/retire-song/assignment",
        json={"ideaId": "retire-idea"},
        headers=_headers(),
    )
    assert rejected.status_code == 409
    assert "Retired" in rejected.json()["detail"]


@pytest.mark.asyncio
async def test_idea_deletion_and_full_replace_free_assigned_songs(
    db_client: AsyncClient,
):
    await db_client.put(
        "/api/data/ideas",
        json=[_idea("delete-song-idea"), _idea("replace-song-idea")],
        headers=_headers(),
    )
    await db_client.put(
        "/api/data/songs",
        json=[_song("delete-song"), _song("replace-song")],
        headers=_headers(),
    )
    await db_client.put(
        "/api/songs/delete-song/assignment",
        json={"ideaId": "delete-song-idea"},
        headers=_headers(),
    )
    await db_client.put(
        "/api/songs/replace-song/assignment",
        json={"ideaId": "replace-song-idea"},
        headers=_headers(),
    )

    deleted = await db_client.delete(
        "/api/ideas/delete-song-idea", headers=_headers()
    )
    assert deleted.status_code == 200
    by_id = {song["id"]: song for song in deleted.json()["data"]["songs"]}
    assert by_id["delete-song"]["status"] == "unused"
    assert by_id["delete-song"]["assignedIdeaId"] is None

    replaced = await db_client.put(
        "/api/data/ideas", json=[], headers=_headers()
    )
    assert replaced.status_code == 200
    songs = (await db_client.get("/api/data/songs", headers=_headers())).json()
    assert all(song["status"] == "unused" for song in songs)
    assert all(song["assignedIdeaId"] is None for song in songs)


@pytest.mark.asyncio
async def test_old_import_without_songs_preserves_song_bank(db_client: AsyncClient):
    await db_client.put(
        "/api/data/songs", json=[_song("preserved-song")], headers=_headers()
    )
    imported = await db_client.put(
        "/api/import",
        json={"config": {"youtubeVideo1": "legacy-backup"}},
        headers=_headers(),
    )
    assert imported.status_code == 200
    assert [song["id"] for song in imported.json()["state"]["songs"]] == [
        "preserved-song"
    ]


@pytest.mark.asyncio
async def test_stale_revision_cannot_overwrite_song_bank(db_client: AsyncClient):
    revision = (await db_client.get("/api/export", headers=_headers())).json()[
        "revision"
    ]
    fresh = await db_client.put(
        "/api/data/songs",
        json=[_song("fresh-song")],
        headers=_headers(**{"If-Match": str(revision)}),
    )
    stale = await db_client.put(
        "/api/data/songs",
        json=[_song("stale-song")],
        headers=_headers(**{"If-Match": str(revision)}),
    )
    assert fresh.status_code == 200
    assert stale.status_code == 409
    assert [
        song["id"]
        for song in (await db_client.get("/api/data/songs", headers=_headers())).json()
    ] == ["fresh-song"]


@pytest.mark.asyncio
async def test_database_constraint_rejects_two_songs_for_one_idea(
    db_session: AsyncSession,
):
    db_session.add(Idea(id="song-constraint-idea"))
    db_session.add_all(
        [
            Song(
                id="song-constraint-one",
                artist="Artist",
                title="One",
                youtube_url="https://youtu.be/abcdefghijk",
                private_notes="",
                status="used",
                assigned_idea_id="song-constraint-idea",
            ),
            Song(
                id="song-constraint-two",
                artist="Artist",
                title="Two",
                youtube_url="https://youtu.be/abcdefghijk",
                private_notes="",
                status="used",
                assigned_idea_id="song-constraint-idea",
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_concurrent_assignments_leave_one_song_on_idea(
    db_session: AsyncSession,
):
    idea_id = "song-concurrent-idea"
    song_ids = ["song-concurrent-one", "song-concurrent-two"]
    db_session.add(Idea(id=idea_id))
    db_session.add_all(
        [
            Song(
                id=song_id,
                artist="Artist",
                title=song_id,
                youtube_url="https://youtu.be/abcdefghijk",
                private_notes="",
                status="unused",
            )
            for song_id in song_ids
        ]
    )
    await db_session.commit()
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def assign(song_id: str) -> None:
        async with factory() as session:
            await assign_song_to_idea(session, song_id, idea_id)
            await session.commit()

    try:
        await asyncio.gather(*(assign(song_id) for song_id in song_ids))
        async with factory() as verify:
            result = await verify.execute(select(Song).where(Song.id.in_(song_ids)))
            songs = list(result.scalars())
            assigned = [song for song in songs if song.assigned_idea_id == idea_id]
            assert len(assigned) == 1
            assert assigned[0].status == "used"
    finally:
        async with factory() as cleanup:
            await cleanup.execute(
                update(Song)
                .where(Song.id.in_(song_ids))
                .values(status="unused", assigned_idea_id=None)
            )
            await cleanup.execute(delete(Song).where(Song.id.in_(song_ids)))
            await cleanup.execute(delete(Idea).where(Idea.id == idea_id))
            await cleanup.commit()


@pytest.mark.asyncio
async def test_private_song_notes_never_appear_in_public_episode_response(
    db_client: AsyncClient,
):
    await db_client.put(
        "/api/data/ideas", json=[_idea("private-song-idea")], headers=_headers()
    )
    await db_client.put(
        "/api/data/songs", json=[_song("private-song")], headers=_headers()
    )
    await db_client.put(
        "/api/songs/private-song/assignment",
        json={"ideaId": "private-song-idea"},
        headers=_headers(),
    )
    response = await db_client.get("/public/episodes")
    assert "Keep this in authenticated preparation views." not in response.text
