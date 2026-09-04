"""Persistence and lifecycle operations for the private reusable Guest Bank."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from satt.crud import bump_data_revision
from satt.episode_numbers import effective_episode_number
from satt.guest_contract import (
    GuestContractError,
    validate_guest_assignments,
    validate_guests,
    validate_opaque_id,
)
from satt.models import Assignment, Guest, GuestAssignment, Idea, ShowSlot
from satt.serializers import serialize_guest, serialize_guest_assignment


_GUEST_LIFECYCLE_LOCK_ID = 0x53415447


class GuestNotFoundError(LookupError):
    """Raised when a guest or idea referenced by a guest operation is missing."""


class GuestLifecycleError(RuntimeError):
    """Raised when a guest lifecycle transition is not allowed."""


async def _lock_guest_lifecycle(db: AsyncSession) -> None:
    await db.execute(select(func.pg_advisory_xact_lock(_GUEST_LIFECYCLE_LOCK_ID)))


async def get_guest_assignments(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(GuestAssignment).order_by(
            GuestAssignment.guest_id,
            GuestAssignment.idea_id,
        )
    )
    return [serialize_guest_assignment(row) for row in result.scalars()]


async def get_guests(db: AsyncSession) -> list[dict]:
    guest_result = await db.execute(select(Guest).order_by(Guest.created_at, Guest.id))
    guests = list(guest_result.scalars())
    effective_release_date = func.coalesce(
        ShowSlot.release_date_override, ShowSlot.release_date
    )
    history_result = await db.execute(
        select(
            GuestAssignment.guest_id,
            GuestAssignment.idea_id,
            Idea.selected_title,
            Assignment.slot_id,
            ShowSlot.episode_number,
            ShowSlot.episode_num,
            ShowSlot.episode_number_override,
            effective_release_date.label("release_date"),
        )
        .join(Idea, Idea.id == GuestAssignment.idea_id)
        .outerjoin(Assignment, Assignment.idea_id == Idea.id)
        .outerjoin(ShowSlot, ShowSlot.id == Assignment.slot_id)
    )
    histories: dict[str, list[dict]] = {}
    for row in history_result:
        histories.setdefault(row.guest_id, []).append(
            {
                "ideaId": row.idea_id,
                "title": row.selected_title,
                "slotId": row.slot_id,
                "episodeNumber": (
                    effective_episode_number(
                        row.episode_number,
                        row.episode_num,
                        row.episode_number_override,
                    )
                    if row.episode_number is not None
                    else None
                ),
                "releaseDate": row.release_date.isoformat()
                if row.release_date is not None
                else None,
                "scheduled": row.release_date is not None,
            }
        )

    serialized: list[dict] = []
    for guest in guests:
        history = histories.get(guest.id, [])
        history.sort(
            key=lambda item: (
                item["releaseDate"] is None,
                item["releaseDate"] or "",
                item["ideaId"],
            )
        )
        dated = [
            date.fromisoformat(item["releaseDate"])
            for item in history
            if item["releaseDate"]
        ]
        serialized.append(
            serialize_guest(
                guest,
                total_appearances=len(history),
                first_appearance=min(dated) if dated else None,
                most_recent_appearance=max(dated) if dated else None,
                appearance_history=history,
            )
        )
    return serialized


async def replace_guests(db: AsyncSession, guests: list[dict]) -> None:
    guests = validate_guests(guests)
    await _lock_guest_lifecycle(db)
    new_ids = {guest["id"] for guest in guests}
    existing_result = await db.execute(select(Guest.id, Guest.created_at))
    created_at_map = {row.id: row.created_at for row in existing_result}
    removed_ids = set(created_at_map) - new_ids
    if removed_ids:
        linked_result = await db.execute(
            select(GuestAssignment.guest_id)
            .where(GuestAssignment.guest_id.in_(removed_ids))
            .limit(1)
        )
        if linked_result.scalar_one_or_none() is not None:
            raise GuestLifecycleError(
                "Assigned guests cannot be deleted; remove every show assignment first"
            )
    if new_ids:
        await db.execute(delete(Guest).where(Guest.id.notin_(new_ids)))
    else:
        await db.execute(delete(Guest))
    now = datetime.now(timezone.utc)
    for guest in guests:
        statement = pg_insert(Guest.__table__).values(
            id=guest["id"],
            display_name=guest["displayName"],
            private_notes=guest["privateNotes"],
            status=guest["status"],
            created_at=created_at_map.get(guest["id"]) or guest.get("createdAt") or now,
            updated_at=now,
        )
        await db.execute(
            statement.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "display_name": statement.excluded.display_name,
                    "private_notes": statement.excluded.private_notes,
                    "status": statement.excluded.status,
                    "updated_at": statement.excluded.updated_at,
                },
            )
        )
    await db.flush()
    await bump_data_revision(db)


async def replace_guest_assignments(
    db: AsyncSession,
    assignments: list[dict],
    *,
    preserved_archived_pairs: set[tuple[str, str]] | None = None,
) -> None:
    assignments = validate_guest_assignments(assignments)
    await _lock_guest_lifecycle(db)
    pairs = {(item["guestId"], item["ideaId"]) for item in assignments}
    guest_ids = {item["guestId"] for item in assignments}
    idea_ids = {item["ideaId"] for item in assignments}

    guest_rows = {}
    if guest_ids:
        result = await db.execute(select(Guest).where(Guest.id.in_(guest_ids)))
        guest_rows = {row.id: row for row in result.scalars()}
    missing_guests = guest_ids - set(guest_rows)
    if missing_guests:
        raise GuestContractError("guestId must reference an existing guest")
    if idea_ids:
        result = await db.execute(select(Idea.id).where(Idea.id.in_(idea_ids)))
        missing_ideas = idea_ids - set(result.scalars())
        if missing_ideas:
            raise GuestContractError("ideaId must reference an existing idea")

    existing_result = await db.execute(
        select(GuestAssignment.guest_id, GuestAssignment.idea_id)
    )
    existing_pairs = {(row.guest_id, row.idea_id) for row in existing_result}
    existing_pairs.update(preserved_archived_pairs or set())
    if any(
        guest_rows[guest_id].status == "archived"
        and (guest_id, idea_id) not in existing_pairs
        for guest_id, idea_id in pairs
    ):
        raise GuestLifecycleError("Archived guests cannot receive new assignments")

    await db.execute(delete(GuestAssignment))
    now = datetime.now(timezone.utc)
    for item in assignments:
        await db.execute(
            pg_insert(GuestAssignment.__table__).values(
                guest_id=item["guestId"],
                idea_id=item["ideaId"],
                assigned_at=item.get("assignedAt") or now,
            )
        )
    await db.flush()
    await bump_data_revision(db)


async def assign_guest_to_idea(db: AsyncSession, guest_id: str, idea_id: str) -> bool:
    guest_id = validate_opaque_id(guest_id, label="guest id")
    idea_id = validate_opaque_id(idea_id, label="idea id")
    await _lock_guest_lifecycle(db)
    guest_result = await db.execute(
        select(Guest).where(Guest.id == guest_id).with_for_update()
    )
    guest = guest_result.scalar_one_or_none()
    if guest is None:
        raise GuestNotFoundError("Guest not found")
    idea_result = await db.execute(select(Idea.id).where(Idea.id == idea_id))
    if idea_result.scalar_one_or_none() is None:
        raise GuestNotFoundError("Idea not found")
    existing = await db.execute(
        select(GuestAssignment.guest_id).where(
            GuestAssignment.guest_id == guest_id,
            GuestAssignment.idea_id == idea_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return False
    if guest.status == "archived":
        raise GuestLifecycleError("Archived guests cannot receive new assignments")
    result = await db.execute(
        pg_insert(GuestAssignment.__table__)
        .values(guest_id=guest_id, idea_id=idea_id)
        .on_conflict_do_nothing(index_elements=["guest_id", "idea_id"])
        .returning(GuestAssignment.guest_id)
    )
    created = result.scalar_one_or_none() is not None
    if created:
        await db.flush()
        await bump_data_revision(db)
    return created


async def unassign_guest_from_idea(
    db: AsyncSession, guest_id: str, idea_id: str
) -> bool:
    guest_id = validate_opaque_id(guest_id, label="guest id")
    idea_id = validate_opaque_id(idea_id, label="idea id")
    await _lock_guest_lifecycle(db)
    result = await db.execute(
        delete(GuestAssignment)
        .where(
            GuestAssignment.guest_id == guest_id,
            GuestAssignment.idea_id == idea_id,
        )
        .returning(GuestAssignment.guest_id)
    )
    removed = result.scalar_one_or_none() is not None
    if removed:
        await db.flush()
        await bump_data_revision(db)
    return removed


async def set_guest_status(db: AsyncSession, guest_id: str, status: str) -> None:
    guest_id = validate_opaque_id(guest_id, label="guest id")
    if status not in {"active", "archived"}:
        raise GuestContractError("status must be active or archived")
    await _lock_guest_lifecycle(db)
    result = await db.execute(
        select(Guest).where(Guest.id == guest_id).with_for_update()
    )
    guest = result.scalar_one_or_none()
    if guest is None:
        raise GuestNotFoundError("Guest not found")
    if guest.status == status:
        return
    await db.execute(
        update(Guest)
        .where(Guest.id == guest_id)
        .values(status=status, updated_at=datetime.now(timezone.utc))
    )
    await db.flush()
    await bump_data_revision(db)


async def delete_guest(db: AsyncSession, guest_id: str) -> None:
    guest_id = validate_opaque_id(guest_id, label="guest id")
    await _lock_guest_lifecycle(db)
    result = await db.execute(
        select(Guest.id).where(Guest.id == guest_id).with_for_update()
    )
    if result.scalar_one_or_none() is None:
        raise GuestNotFoundError("Guest not found")
    linked = await db.execute(
        select(GuestAssignment.guest_id)
        .where(GuestAssignment.guest_id == guest_id)
        .limit(1)
    )
    if linked.scalar_one_or_none() is not None:
        raise GuestLifecycleError(
            "Assigned guests cannot be deleted; remove every show assignment first"
        )
    await db.execute(delete(Guest).where(Guest.id == guest_id))
    await db.flush()
    await bump_data_revision(db)
