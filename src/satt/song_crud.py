"""Database lifecycle operations for the private Song Bank."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from satt.crud import bump_data_revision, _lock_song_lifecycle
from satt.models import Idea, Song
from satt.serializers import serialize_song
from satt.song_contract import SongContractError, validate_banked_songs


class SongNotFoundError(LookupError):
    """Raised when a requested Song Bank resource does not exist."""


class SongLifecycleError(RuntimeError):
    """Raised when a requested Song Bank lifecycle transition is invalid."""


def _parse_dt(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def get_songs(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(Song).order_by(Song.created_at, Song.id))
    return [serialize_song(row) for row in result.scalars()]


async def replace_songs(db: AsyncSession, songs: list[dict]) -> None:
    songs = validate_banked_songs(songs)
    await _lock_song_lifecycle(db)

    assigned_ids = {
        song["assignedIdeaId"] for song in songs if song["assignedIdeaId"] is not None
    }
    if assigned_ids:
        result = await db.execute(select(Idea.id).where(Idea.id.in_(assigned_ids)))
        existing_ids = set(result.scalars())
        missing_ids = assigned_ids - existing_ids
        if missing_ids:
            raise SongContractError("assignedIdeaId must reference an existing idea")

    new_ids = {song["id"] for song in songs}
    result = await db.execute(select(Song.id, Song.created_at))
    created_at_map = {row.id: row.created_at for row in result}

    if new_ids:
        await db.execute(delete(Song).where(Song.id.notin_(new_ids)))
    else:
        await db.execute(delete(Song))
    await db.flush()

    await db.execute(update(Song).values(status="unused", assigned_idea_id=None))
    await db.flush()

    now = datetime.now(timezone.utc)
    for song in songs:
        stmt = pg_insert(Song.__table__).values(
            id=song["id"],
            artist=song["artist"],
            title=song["title"],
            youtube_url=song["youtubeUrl"],
            private_notes=song["privateNotes"],
            status=song["status"],
            assigned_idea_id=song["assignedIdeaId"],
            created_at=created_at_map.get(song["id"])
            or _parse_dt(song.get("createdAt"))
            or now,
            updated_at=now,
        )
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "artist": stmt.excluded.artist,
                    "title": stmt.excluded.title,
                    "youtube_url": stmt.excluded.youtube_url,
                    "private_notes": stmt.excluded.private_notes,
                    "status": stmt.excluded.status,
                    "assigned_idea_id": stmt.excluded.assigned_idea_id,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
        )
    await db.flush()
    await bump_data_revision(db)


async def assign_song_to_idea(
    db: AsyncSession, song_id: str, idea_id: str
) -> None:
    """Atomically move a song and replace any song already assigned to the idea."""
    await _lock_song_lifecycle(db)
    idea_result = await db.execute(
        select(Idea.id).where(Idea.id == idea_id).with_for_update()
    )
    if idea_result.scalar_one_or_none() is None:
        raise SongNotFoundError("Idea not found")

    song_result = await db.execute(
        select(Song).where(Song.id == song_id).with_for_update()
    )
    song = song_result.scalar_one_or_none()
    if song is None:
        raise SongNotFoundError("Song not found")
    if song.status == "retired":
        raise SongLifecycleError("Retired songs cannot be assigned")

    await db.execute(
        update(Song)
        .where(Song.assigned_idea_id == idea_id, Song.id != song_id)
        .values(status="unused", assigned_idea_id=None, updated_at=datetime.now(timezone.utc))
    )
    await db.flush()
    await db.execute(
        update(Song)
        .where(Song.id == song_id)
        .values(
            status="used",
            assigned_idea_id=idea_id,
            updated_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()
    await bump_data_revision(db)


async def free_song(db: AsyncSession, song_id: str) -> None:
    await _lock_song_lifecycle(db)
    result = await db.execute(select(Song).where(Song.id == song_id).with_for_update())
    song = result.scalar_one_or_none()
    if song is None:
        raise SongNotFoundError("Song not found")
    status = "retired" if song.status == "retired" else "unused"
    await db.execute(
        update(Song)
        .where(Song.id == song_id)
        .values(status=status, assigned_idea_id=None, updated_at=datetime.now(timezone.utc))
    )
    await db.flush()
    await bump_data_revision(db)


async def set_song_status(db: AsyncSession, song_id: str, status: str) -> None:
    if status not in {"unused", "retired"}:
        raise SongLifecycleError("Song status must be unused or retired")
    await _lock_song_lifecycle(db)
    result = await db.execute(select(Song.id).where(Song.id == song_id).with_for_update())
    if result.scalar_one_or_none() is None:
        raise SongNotFoundError("Song not found")
    await db.execute(
        update(Song)
        .where(Song.id == song_id)
        .values(status=status, assigned_idea_id=None, updated_at=datetime.now(timezone.utc))
    )
    await db.flush()
    await bump_data_revision(db)


async def delete_song(db: AsyncSession, song_id: str) -> None:
    await _lock_song_lifecycle(db)
    result = await db.execute(select(Song.id).where(Song.id == song_id).with_for_update())
    if result.scalar_one_or_none() is None:
        raise SongNotFoundError("Song not found")
    await db.execute(delete(Song).where(Song.id == song_id))
    await db.flush()
    await bump_data_revision(db)
