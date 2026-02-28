"""Database read/write helpers. Routes call these; they never query the DB directly."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pytz
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from satt.models import Assignment, Config, Idea, Joke, ShowSlot
from satt.serializers import serialize_idea, serialize_joke, serialize_show_slot

_PST = pytz.timezone("America/Los_Angeles")


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


# ---------------------------------------------------------------------------
# Ideas
# ---------------------------------------------------------------------------


async def get_ideas(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(Idea).order_by(Idea.created_at))
    return [serialize_idea(row) for row in result.scalars()]


async def replace_ideas(db: AsyncSession, ideas: list[dict]) -> None:
    new_ids = {idea["id"] for idea in ideas}

    # Preserve created_at for existing rows
    result = await db.execute(select(Idea.id, Idea.created_at))
    created_at_map: dict[str, datetime] = {row.id: row.created_at for row in result}

    # Delete rows not in new set (cascade removes their assignments)
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
        updated_at_val = _parse_dt(idea.get("updatedAt")) or datetime.now(timezone.utc)

        stmt = pg_insert(Idea.__table__).values(
            id=iid,
            titles=idea.get("titles") or [],
            selected_title=idea.get("selectedTitle"),
            summary=idea.get("summary"),
            outline=idea.get("outline") or [],
            status=idea.get("status") or "draft",
            image_file_id=idea.get("imageFileId"),
            raw_notes=idea.get("rawNotes"),
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
                "updated_at": stmt.excluded.updated_at,
                # created_at intentionally omitted — preserve original
            },
        )
        await db.execute(ins)
    await db.flush()


# ---------------------------------------------------------------------------
# Jokes
# ---------------------------------------------------------------------------


async def get_jokes(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(Joke).order_by(Joke.created_at))
    return [serialize_joke(row) for row in result.scalars()]


async def replace_jokes(db: AsyncSession, jokes: list[dict]) -> None:
    new_ids = {joke["id"] for joke in jokes}

    result = await db.execute(select(Joke.id, Joke.created_at))
    created_at_map: dict[str, datetime] = {row.id: row.created_at for row in result}

    if new_ids:
        await db.execute(delete(Joke).where(Joke.id.notin_(new_ids)))
    else:
        await db.execute(delete(Joke))
    await db.flush()

    for joke in jokes:
        jid = joke["id"]
        orig_created_at = created_at_map.get(jid)
        created_at_val = orig_created_at or _parse_dt(joke.get("createdAt")) or datetime.now(timezone.utc)

        stmt = pg_insert(Joke.__table__).values(
            id=jid,
            text=joke.get("text") or "",
            status=joke.get("status") or "active",
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


# ---------------------------------------------------------------------------
# Show Slots
# ---------------------------------------------------------------------------


async def get_show_slots(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(ShowSlot).order_by(ShowSlot.release_date))
    return [serialize_show_slot(row) for row in result.scalars()]


async def replace_show_slots(db: AsyncSession, slots: list[dict]) -> None:
    new_ids = {slot["id"] for slot in slots}

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


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------


async def get_assignments(db: AsyncSession) -> dict:
    result = await db.execute(select(Assignment.slot_id, Assignment.idea_id))
    return {row.slot_id: row.idea_id for row in result}


async def replace_assignments(db: AsyncSession, assignments: dict) -> None:
    await db.execute(delete(Assignment))
    await db.flush()

    for slot_id, idea_id in assignments.items():
        stmt = pg_insert(Assignment.__table__).values(
            slot_id=slot_id, idea_id=idea_id
        ).on_conflict_do_update(
            index_elements=["slot_id"],
            set_={"idea_id": pg_insert(Assignment.__table__).excluded.idea_id},
        )
        await db.execute(stmt)
    await db.flush()


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
