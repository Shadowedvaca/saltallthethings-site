"""Database read/write helpers. Routes call these; they never query the DB directly."""

from __future__ import annotations

from datetime import date, datetime, timezone
import pytz
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from satt.joke_contract import validate_banked_jokes
from satt.models import Assignment, Config, DataRevision, Idea, Joke, ShowSlot, Song
from satt.serializers import serialize_idea, serialize_joke, serialize_postprod_row, serialize_show_slot

_PST = pytz.timezone("America/Los_Angeles")
_JOKE_LIFECYCLE_LOCK_ID = 0x53415454
_SONG_LIFECYCLE_LOCK_ID = 0x5341544F
_SCHEDULE_LIFECYCLE_LOCK_ID = 0x53415453


class DataNotFoundError(LookupError):
    """Raised when a requested lifecycle resource does not exist."""


class DataConflictError(RuntimeError):
    """Raised when a client attempts to mutate an obsolete data snapshot."""

    def __init__(self, current_revision: int):
        super().__init__("The server data changed after this page loaded.")
        self.current_revision = current_revision


async def get_data_revision(db: AsyncSession) -> int:
    result = await db.execute(
        select(DataRevision.revision).where(DataRevision.id == 1)
    )
    return result.scalar_one()


async def require_data_revision(db: AsyncSession, expected_revision: int) -> None:
    result = await db.execute(
        select(DataRevision.revision)
        .where(DataRevision.id == 1)
        .with_for_update()
    )
    current_revision = result.scalar_one()
    if current_revision != expected_revision:
        raise DataConflictError(current_revision)


async def bump_data_revision(db: AsyncSession) -> int:
    result = await db.execute(
        update(DataRevision)
        .where(DataRevision.id == 1)
        .values(revision=DataRevision.revision + 1)
        .returning(DataRevision.revision)
    )
    return result.scalar_one()


async def _lock_joke_lifecycle(db: AsyncSession) -> None:
    """Serialize the small bank's lifecycle writes to avoid cross-swap deadlocks."""
    await db.execute(select(func.pg_advisory_xact_lock(_JOKE_LIFECYCLE_LOCK_ID)))


async def _lock_song_lifecycle(db: AsyncSession) -> None:
    """Serialize Song Bank lifecycle writes and assignment swaps."""
    await db.execute(select(func.pg_advisory_xact_lock(_SONG_LIFECYCLE_LOCK_ID)))


async def _lock_schedule_lifecycle(db: AsyncSession) -> None:
    """Serialize schedule writes so moves cannot create transient duplicates."""
    await db.execute(
        select(func.pg_advisory_xact_lock(_SCHEDULE_LIFECYCLE_LOCK_ID))
    )


# ---------------------------------------------------------------------------
# Datetime parsing helper
# ---------------------------------------------------------------------------


def _parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    value = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def _parse_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


async def get_config(db: AsyncSession) -> dict:
    result = await db.execute(select(Config))
    row = result.scalar_one_or_none()
    return row.data if row else {}


async def save_config(db: AsyncSession, data: dict) -> None:
    stmt = pg_insert(Config).values(id=1, data=data).on_conflict_do_update(
        index_elements=["id"], set_={"data": pg_insert(Config).excluded.data}
    )
    await db.execute(stmt)
    await db.flush()
    await bump_data_revision(db)


# ---------------------------------------------------------------------------
# Ideas
# ---------------------------------------------------------------------------


async def get_ideas(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(Idea).order_by(Idea.created_at))
    return [serialize_idea(row) for row in result.scalars()]


async def get_idea_and_slot(
    db: AsyncSession, idea_id: str
) -> tuple[Idea | None, ShowSlot | None]:
    """Return (Idea, ShowSlot) for an idea_id. ShowSlot may be None if not assigned."""
    result = await db.execute(
        select(Idea, ShowSlot)
        .outerjoin(Assignment, Assignment.idea_id == Idea.id)
        .outerjoin(ShowSlot, ShowSlot.id == Assignment.slot_id)
        .where(Idea.id == idea_id)
    )
    row = result.one_or_none()
    if row is None:
        return None, None
    return row[0], row[1]


async def replace_ideas(db: AsyncSession, ideas: list[dict]) -> None:
    await _lock_joke_lifecycle(db)
    await _lock_song_lifecycle(db)
    new_ids = {idea["id"] for idea in ideas}

    # Preserve created_at for existing rows
    result = await db.execute(select(Idea.id, Idea.created_at))
    created_at_map: dict[str, datetime] = {row.id: row.created_at for row in result}
    deleted_ids = set(created_at_map) - new_ids

    # Free opening jokes in the same transaction before removed ideas cascade.
    if deleted_ids:
        await db.execute(
            update(Joke)
            .where(Joke.used_by_idea_id.in_(deleted_ids))
            .values(status="unused", used_by_idea_id=None)
        )
        await db.execute(
            update(Song)
            .where(Song.assigned_idea_id.in_(deleted_ids))
            .values(
                status="unused",
                assigned_idea_id=None,
                updated_at=datetime.now(timezone.utc),
            )
        )

    # Delete rows not in new set (cascade removes their schedule assignments).
    if new_ids:
        await db.execute(delete(Idea).where(Idea.id.notin_(new_ids)))
    else:
        await db.execute(delete(Idea))
    await db.flush()

    # Upsert each idea
    for idea in ideas:
        iid = idea["id"]
        orig_created_at = created_at_map.get(iid)
        created_at_val = orig_created_at or _parse_dt(idea.get("createdAt")) or datetime.now(timezone.utc)
        updated_at_val = datetime.now(timezone.utc)

        stmt = pg_insert(Idea.__table__).values(
            id=iid,
            titles=idea.get("titles") or [],
            selected_title=idea.get("selectedTitle"),
            summary=idea.get("summary"),
            outline=idea.get("outline") or [],
            status=idea.get("status") or "draft",
            image_file_id=idea.get("imageFileId"),
            raw_notes=idea.get("rawNotes"),
            ai_provider=idea.get("aiProvider") or idea.get("aiModel"),
            ai_model_id=idea.get("aiModelId"),
            created_at=created_at_val,
            updated_at=updated_at_val,
        )
        ins = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "titles": stmt.excluded.titles,
                "selected_title": stmt.excluded.selected_title,
                "summary": stmt.excluded.summary,
                "outline": stmt.excluded.outline,
                "status": stmt.excluded.status,
                "image_file_id": stmt.excluded.image_file_id,
                "raw_notes": stmt.excluded.raw_notes,
                "ai_provider": stmt.excluded.ai_provider,
                "ai_model_id": stmt.excluded.ai_model_id,
                "updated_at": stmt.excluded.updated_at,
                # created_at intentionally omitted — preserve original
            },
        )
        await db.execute(ins)
    await db.flush()
    await bump_data_revision(db)


# ---------------------------------------------------------------------------
# Jokes
# ---------------------------------------------------------------------------


async def get_jokes(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(Joke).order_by(Joke.created_at))
    return [serialize_joke(row) for row in result.scalars()]


async def replace_jokes(db: AsyncSession, jokes: list[dict]) -> None:
    jokes = validate_banked_jokes(jokes)
    await _lock_joke_lifecycle(db)
    new_ids = {joke["id"] for joke in jokes}

    result = await db.execute(select(Joke.id, Joke.created_at))
    created_at_map: dict[str, datetime] = {row.id: row.created_at for row in result}

    if new_ids:
        await db.execute(delete(Joke).where(Joke.id.notin_(new_ids)))
    else:
        await db.execute(delete(Joke))
    await db.flush()

    # Remove transient assignments before upserts so valid assignment swaps do
    # not collide with the uniqueness constraint partway through the batch.
    await db.execute(
        update(Joke).values(status="unused", used_by_idea_id=None)
    )
    await db.flush()

    for joke in jokes:
        jid = joke["id"]
        orig_created_at = created_at_map.get(jid)
        created_at_val = orig_created_at or _parse_dt(joke.get("createdAt")) or datetime.now(timezone.utc)

        stmt = pg_insert(Joke.__table__).values(
            id=jid,
            text=joke["text"],
            status=joke["status"],
            source=joke.get("source") or "manual",
            used_by_idea_id=joke.get("usedByIdeaId"),
            created_at=created_at_val,
        )
        ins = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "text": stmt.excluded.text,
                "status": stmt.excluded.status,
                "source": stmt.excluded.source,
                "used_by_idea_id": stmt.excluded.used_by_idea_id,
            },
        )
        await db.execute(ins)
    await db.flush()
    await bump_data_revision(db)


async def assign_joke_to_idea(
    db: AsyncSession,
    joke_id: str,
    idea_id: str,
) -> None:
    """Atomically replace an idea's opening joke with the selected bank entry."""
    await _lock_joke_lifecycle(db)
    idea_result = await db.execute(
        select(Idea.id).where(Idea.id == idea_id).with_for_update()
    )
    if idea_result.scalar_one_or_none() is None:
        raise DataNotFoundError("Idea not found")

    joke_result = await db.execute(
        select(Joke.id).where(Joke.id == joke_id).with_for_update()
    )
    if joke_result.scalar_one_or_none() is None:
        raise DataNotFoundError("Joke not found")

    await db.execute(
        update(Joke)
        .where(Joke.used_by_idea_id == idea_id)
        .values(status="unused", used_by_idea_id=None)
    )
    await db.flush()
    await db.execute(
        update(Joke)
        .where(Joke.id == joke_id)
        .values(status="used", used_by_idea_id=idea_id)
    )
    await db.flush()
    await bump_data_revision(db)


async def free_joke(db: AsyncSession, joke_id: str) -> None:
    await _lock_joke_lifecycle(db)
    result = await db.execute(
        select(Joke.id).where(Joke.id == joke_id).with_for_update()
    )
    if result.scalar_one_or_none() is None:
        raise DataNotFoundError("Joke not found")
    await db.execute(
        update(Joke)
        .where(Joke.id == joke_id)
        .values(status="unused", used_by_idea_id=None)
    )
    await db.flush()
    await bump_data_revision(db)


async def delete_idea(db: AsyncSession, idea_id: str) -> None:
    """Delete one idea while freeing its assigned bank entries atomically."""
    await _lock_joke_lifecycle(db)
    await _lock_song_lifecycle(db)
    result = await db.execute(
        select(Idea.id).where(Idea.id == idea_id).with_for_update()
    )
    if result.scalar_one_or_none() is None:
        raise DataNotFoundError("Idea not found")
    await db.execute(
        update(Joke)
        .where(Joke.used_by_idea_id == idea_id)
        .values(status="unused", used_by_idea_id=None)
    )
    await db.execute(
        update(Song)
        .where(Song.assigned_idea_id == idea_id)
        .values(
            status="unused",
            assigned_idea_id=None,
            updated_at=datetime.now(timezone.utc),
        )
    )
    await db.execute(delete(Idea).where(Idea.id == idea_id))
    await db.flush()
    await bump_data_revision(db)


# ---------------------------------------------------------------------------
# Show Slots
# ---------------------------------------------------------------------------


async def get_show_slots(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(ShowSlot).order_by(ShowSlot.release_date))
    return [serialize_show_slot(row) for row in result.scalars()]


async def replace_show_slots(db: AsyncSession, slots: list[dict]) -> None:
    await _lock_schedule_lifecycle(db)
    new_ids = {slot["id"] for slot in slots}
    existing_result = await db.execute(select(ShowSlot.id))
    deleted_ids = {row.id for row in existing_result} - new_ids

    if deleted_ids:
        displaced_result = await db.execute(
            select(Assignment.idea_id).where(Assignment.slot_id.in_(deleted_ids))
        )
        displaced_idea_ids = {row.idea_id for row in displaced_result}
        if displaced_idea_ids:
            await db.execute(
                update(Idea)
                .where(Idea.id.in_(displaced_idea_ids))
                .values(status="processed", updated_at=datetime.now(timezone.utc))
            )

    if new_ids:
        await db.execute(delete(ShowSlot).where(ShowSlot.id.notin_(new_ids)))
    else:
        await db.execute(delete(ShowSlot))
    await db.flush()

    for slot in slots:
        sid = slot["id"]
        stmt = pg_insert(ShowSlot.__table__).values(
            id=sid,
            episode_number=slot.get("episodeNumber") or "",
            episode_num=slot.get("episodeNum") or 0,
            record_date=_parse_date(slot.get("recordDate")),
            release_date=_parse_date(slot.get("releaseDate")),
            is_rollout=slot.get("isRollout") or False,
            release_date_override=_parse_date(slot.get("releaseDateOverride")),
        )
        ins = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "episode_number": stmt.excluded.episode_number,
                "episode_num": stmt.excluded.episode_num,
                "record_date": stmt.excluded.record_date,
                "release_date": stmt.excluded.release_date,
                "is_rollout": stmt.excluded.is_rollout,
                "release_date_override": stmt.excluded.release_date_override,
            },
        )
        await db.execute(ins)
    await db.flush()
    await bump_data_revision(db)


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------


async def get_assignments(db: AsyncSession) -> dict:
    result = await db.execute(select(Assignment.slot_id, Assignment.idea_id))
    return {row.slot_id: row.idea_id for row in result}


async def replace_assignments(db: AsyncSession, assignments: dict) -> None:
    idea_ids = list(assignments.values())
    if len(idea_ids) != len(set(idea_ids)):
        raise ValueError("An idea may only be assigned to one show slot")

    await _lock_schedule_lifecycle(db)
    scheduled_result = await db.execute(select(Assignment.idea_id))
    prior_idea_ids = {row.idea_id for row in scheduled_result}
    if prior_idea_ids:
        await db.execute(
            update(Idea)
            .where(Idea.id.in_(prior_idea_ids))
            .values(status="processed", updated_at=datetime.now(timezone.utc))
        )

    await db.execute(delete(Assignment))
    await db.flush()

    for slot_id, idea_id in assignments.items():
        await db.execute(
            pg_insert(Assignment.__table__).values(slot_id=slot_id, idea_id=idea_id)
        )
    if idea_ids:
        await db.execute(
            update(Idea)
            .where(Idea.id.in_(idea_ids))
            .values(status="scheduled", updated_at=datetime.now(timezone.utc))
        )
    await db.flush()
    await bump_data_revision(db)


async def assign_idea_to_slot(
    db: AsyncSession, idea_id: str, slot_id: str
) -> None:
    """Atomically move an idea to a slot and repair displaced idea statuses."""
    await _lock_schedule_lifecycle(db)
    idea_result = await db.execute(
        select(Idea.id).where(Idea.id == idea_id).with_for_update()
    )
    if idea_result.scalar_one_or_none() is None:
        raise DataNotFoundError("Idea not found")
    slot_result = await db.execute(
        select(ShowSlot.id).where(ShowSlot.id == slot_id).with_for_update()
    )
    if slot_result.scalar_one_or_none() is None:
        raise DataNotFoundError("Show slot not found")

    displaced_result = await db.execute(
        select(Assignment.idea_id).where(
            (Assignment.slot_id == slot_id) | (Assignment.idea_id == idea_id)
        )
    )
    displaced_ids = {
        row.idea_id for row in displaced_result if row.idea_id != idea_id
    }
    await db.execute(
        delete(Assignment).where(
            (Assignment.slot_id == slot_id) | (Assignment.idea_id == idea_id)
        )
    )
    if displaced_ids:
        await db.execute(
            update(Idea)
            .where(Idea.id.in_(displaced_ids))
            .values(status="processed", updated_at=datetime.now(timezone.utc))
        )
    await db.execute(
        pg_insert(Assignment.__table__).values(slot_id=slot_id, idea_id=idea_id)
    )
    await db.execute(
        update(Idea)
        .where(Idea.id == idea_id)
        .values(status="scheduled", updated_at=datetime.now(timezone.utc))
    )
    await db.flush()
    await bump_data_revision(db)


async def unassign_idea_from_slot(db: AsyncSession, slot_id: str) -> None:
    """Atomically unassign a slot and return its idea to processed state."""
    await _lock_schedule_lifecycle(db)
    result = await db.execute(
        select(Assignment.idea_id)
        .where(Assignment.slot_id == slot_id)
        .with_for_update()
    )
    idea_id = result.scalar_one_or_none()
    if idea_id is None:
        raise DataNotFoundError("Schedule assignment not found")
    await db.execute(delete(Assignment).where(Assignment.slot_id == slot_id))
    await db.execute(
        update(Idea)
        .where(Idea.id == idea_id)
        .values(status="processed", updated_at=datetime.now(timezone.utc))
    )
    await db.flush()
    await bump_data_revision(db)


# ---------------------------------------------------------------------------
# Post-production queue
# ---------------------------------------------------------------------------


async def get_postproduction_queue(db: AsyncSession) -> list[dict]:
    today = datetime.now(_PST).date()
    result = await db.execute(
        select(ShowSlot, Idea)
        .outerjoin(Assignment, Assignment.slot_id == ShowSlot.id)
        .outerjoin(Idea, Idea.id == Assignment.idea_id)
        .where(ShowSlot.record_date <= today)
        .order_by(ShowSlot.record_date.desc())
    )
    return [serialize_postprod_row(slot, idea) for slot, idea in result.all()]


async def set_production_file_key(db: AsyncSession, slot_id: str, key: str) -> None:
    await db.execute(
        update(ShowSlot)
        .where(ShowSlot.id == slot_id)
        .values(production_file_key=key)
    )
    await db.flush()
    await bump_data_revision(db)


async def set_asset_inventory(db: AsyncSession, slot_id: str, inventory: dict) -> None:
    await db.execute(
        update(ShowSlot)
        .where(ShowSlot.id == slot_id)
        .values(asset_inventory=inventory)
    )
    await db.flush()
    await bump_data_revision(db)


async def set_idea_image_file_id(db: AsyncSession, idea_id: str, file_id: str) -> None:
    await db.execute(
        update(Idea)
        .where(Idea.id == idea_id)
        .values(image_file_id=file_id)
    )
    await db.flush()
    await bump_data_revision(db)


async def set_transcription_job(db: AsyncSession, slot_id: str, job: dict | None) -> None:
    await db.execute(
        update(ShowSlot)
        .where(ShowSlot.id == slot_id)
        .values(transcription_job=job)
    )
    await db.flush()
    await bump_data_revision(db)


async def get_pending_transcription_jobs(db: AsyncSession) -> list[dict]:
    """Return slots with transcription_job.status = 'pending'."""
    result = await db.execute(
        select(ShowSlot.id, ShowSlot.production_file_key)
        .where(ShowSlot.transcription_job["status"].astext == "pending")
        .where(ShowSlot.production_file_key.is_not(None))
    )
    return [{"slotId": row.id, "productionFileKey": row.production_file_key} for row in result]


async def get_slots_for_scan(db: AsyncSession) -> list[dict]:
    """Return slots with a past record_date and a non-null production_file_key."""
    today = datetime.now(_PST).date()
    result = await db.execute(
        select(ShowSlot.id, ShowSlot.production_file_key)
        .where(ShowSlot.record_date <= today)
        .where(ShowSlot.production_file_key.is_not(None))
    )
    return [{"slot_id": row.id, "production_file_key": row.production_file_key} for row in result]


# ---------------------------------------------------------------------------
# Public: released episodes
# ---------------------------------------------------------------------------


async def get_released_episodes(
    db: AsyncSession, page: int, limit: int
) -> dict:
    today_pst: date = datetime.now(_PST).date()

    effective_date = func.coalesce(
        ShowSlot.release_date_override, ShowSlot.release_date
    ).label("effective_release_date")

    base_q = (
        select(
            ShowSlot.episode_number,
            Idea.selected_title,
            Idea.summary,
            Idea.image_file_id,
            effective_date,
        )
        .join(Assignment, Assignment.slot_id == ShowSlot.id)
        .join(Idea, Idea.id == Assignment.idea_id)
        .where(
            func.coalesce(ShowSlot.release_date_override, ShowSlot.release_date)
            <= today_pst
        )
        .order_by(effective_date.desc())
    )

    count_result = await db.execute(
        select(func.count()).select_from(base_q.subquery())
    )
    total = count_result.scalar() or 0

    offset = (page - 1) * limit
    rows_result = await db.execute(base_q.offset(offset).limit(limit))
    rows = rows_result.all()

    episodes = [
        {
            "episodeNumber": row.episode_number,
            "title": row.selected_title,
            "summary": row.summary,
            "imageFileId": row.image_file_id,
            "releaseDate": row.effective_release_date.isoformat(),
        }
        for row in rows
    ]

    return {"episodes": episodes, "page": page, "limit": limit, "total": total}


# ---------------------------------------------------------------------------
# Public: homepage config
# ---------------------------------------------------------------------------


async def get_homepage_config(db: AsyncSession) -> dict:
    cfg = await get_config(db)
    return {
        "youtubeVideo1": cfg.get("youtubeVideo1"),
        "youtubeVideo2": cfg.get("youtubeVideo2"),
        "youtubeVideo3": cfg.get("youtubeVideo3"),
    }
