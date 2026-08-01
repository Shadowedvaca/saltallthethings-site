"""Transactional Top 3 persistence and viewer-scoped privacy projection."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from satt.crud import bump_data_revision, get_data_revision
from satt.models import (
    Idea,
    Top3Assignment,
    Top3Concept,
    Top3Reveal,
    Top3Submission,
    User,
)
from satt.serializers import serialize_top3_concept, serialize_top3_submission

_TOP3_LIFECYCLE_LOCK_ID = 0x53415433


class Top3NotFoundError(LookupError):
    pass


class Top3ConflictError(RuntimeError):
    pass


async def _lock_top3_lifecycle(db: AsyncSession) -> None:
    await db.execute(select(func.pg_advisory_xact_lock(_TOP3_LIFECYCLE_LOCK_ID)))


async def list_concepts(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Top3Concept).order_by(Top3Concept.created_at, Top3Concept.id)
    )
    return [serialize_top3_concept(row) for row in result.scalars()]


async def create_concept(db: AsyncSession, concept: dict, user_id: int) -> dict:
    await _lock_top3_lifecycle(db)
    existing = await db.scalar(
        select(Top3Concept.id).where(Top3Concept.id == concept["id"])
    )
    if existing is not None:
        raise Top3ConflictError("Top 3 concept id already exists")
    row = Top3Concept(
        id=concept["id"],
        name=concept["name"],
        description=concept["description"],
        rules=concept["rules"],
        host_notes=concept["hostNotes"],
        ai_example=concept["aiExample"],
        status=concept["status"],
        source=concept["source"],
        ai_provider=concept["aiProvider"],
        ai_model_id=concept["aiModelId"],
        ai_generated_at=concept["aiGeneratedAt"],
        created_by_user_id=user_id,
    )
    db.add(row)
    await db.flush()
    await bump_data_revision(db)
    return serialize_top3_concept(row)


async def update_concept(db: AsyncSession, concept: dict) -> dict:
    await _lock_top3_lifecycle(db)
    row = await db.scalar(
        select(Top3Concept)
        .where(Top3Concept.id == concept["id"])
        .with_for_update()
    )
    if row is None:
        raise Top3NotFoundError("Top 3 concept not found")
    row.name = concept["name"]
    row.description = concept["description"]
    row.rules = concept["rules"]
    row.host_notes = concept["hostNotes"]
    row.ai_example = concept["aiExample"]
    row.status = concept["status"]
    row.source = concept["source"]
    row.ai_provider = concept["aiProvider"]
    row.ai_model_id = concept["aiModelId"]
    row.ai_generated_at = concept["aiGeneratedAt"]
    row.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await bump_data_revision(db)
    return serialize_top3_concept(row)


async def delete_concept(db: AsyncSession, concept_id: str) -> None:
    await _lock_top3_lifecycle(db)
    row = await db.scalar(
        select(Top3Concept)
        .where(Top3Concept.id == concept_id)
        .with_for_update()
    )
    if row is None:
        raise Top3NotFoundError("Top 3 concept not found")
    assigned = await db.scalar(
        select(Top3Assignment.idea_id).where(Top3Assignment.concept_id == concept_id)
    )
    if assigned is not None:
        raise Top3ConflictError("Assigned Top 3 concepts cannot be deleted")
    await db.delete(row)
    await db.flush()
    await bump_data_revision(db)


async def assign_concept(
    db: AsyncSession, *, idea_id: str, concept_id: str, user_id: int
) -> None:
    await _lock_top3_lifecycle(db)
    idea = await db.scalar(select(Idea.id).where(Idea.id == idea_id).with_for_update())
    if idea is None:
        raise Top3NotFoundError("Idea not found")
    concept = await db.scalar(
        select(Top3Concept)
        .where(Top3Concept.id == concept_id)
        .with_for_update()
    )
    if concept is None:
        raise Top3NotFoundError("Top 3 concept not found")
    if concept.status == "retired":
        raise Top3ConflictError("Retired Top 3 concepts cannot be assigned")

    assignment = await db.scalar(
        select(Top3Assignment)
        .where(Top3Assignment.idea_id == idea_id)
        .with_for_update()
    )
    now = datetime.now(timezone.utc)
    if assignment is None:
        db.add(
            Top3Assignment(
                idea_id=idea_id,
                concept_id=concept_id,
                assigned_by_user_id=user_id,
                assigned_at=now,
                updated_at=now,
            )
        )
    elif assignment.concept_id != concept_id:
        # Picks belong to one immutable assignment definition. Replacing the
        # concept removes its submissions and reveal audit rows atomically.
        await db.execute(
            delete(Top3Assignment).where(Top3Assignment.idea_id == idea_id)
        )
        await db.flush()
        db.add(
            Top3Assignment(
                idea_id=idea_id,
                concept_id=concept_id,
                assigned_by_user_id=user_id,
                assigned_at=now,
                updated_at=now,
            )
        )
    else:
        assignment.assigned_by_user_id = user_id
        assignment.updated_at = now
    await db.flush()
    await bump_data_revision(db)


async def remove_assignment(db: AsyncSession, idea_id: str) -> None:
    await _lock_top3_lifecycle(db)
    assignment = await db.scalar(
        select(Top3Assignment.idea_id)
        .where(Top3Assignment.idea_id == idea_id)
        .with_for_update()
    )
    if assignment is None:
        raise Top3NotFoundError("Top 3 assignment not found")
    await db.execute(delete(Top3Assignment).where(Top3Assignment.idea_id == idea_id))
    await db.flush()
    await bump_data_revision(db)


async def save_current_submission(
    db: AsyncSession,
    *,
    idea_id: str,
    user_id: int,
    submission: dict,
) -> None:
    await _lock_top3_lifecycle(db)
    assignment = await db.scalar(
        select(Top3Assignment.idea_id)
        .where(Top3Assignment.idea_id == idea_id)
        .with_for_update()
    )
    if assignment is None:
        raise Top3NotFoundError("Top 3 assignment not found")
    row = await db.scalar(
        select(Top3Submission)
        .where(
            Top3Submission.assignment_idea_id == idea_id,
            Top3Submission.account_user_id == user_id,
            Top3Submission.participant_type == "account",
        )
        .with_for_update()
    )
    now = datetime.now(timezone.utc)
    if row is None:
        duplicate_id = await db.scalar(
            select(Top3Submission.id).where(Top3Submission.id == submission["id"])
        )
        if duplicate_id is not None:
            raise Top3ConflictError("Top 3 submission id already exists")
        row = Top3Submission(
            id=submission["id"],
            assignment_idea_id=idea_id,
            participant_type="account",
            account_user_id=user_id,
            pick_1=submission["picks"][0],
            pick_2=submission["picks"][1],
            pick_3=submission["picks"][2],
            private_discussion_notes=submission["privateDiscussionNotes"],
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        if row.id != submission["id"]:
            raise Top3ConflictError("Existing submissions keep their original id")
        row.pick_1, row.pick_2, row.pick_3 = submission["picks"]
        row.private_discussion_notes = submission["privateDiscussionNotes"]
        row.updated_at = now
    await db.flush()
    await bump_data_revision(db)


async def delete_current_submission(
    db: AsyncSession, *, idea_id: str, user_id: int
) -> None:
    await _lock_top3_lifecycle(db)
    row = await db.scalar(
        select(Top3Submission.id)
        .where(
            Top3Submission.assignment_idea_id == idea_id,
            Top3Submission.account_user_id == user_id,
            Top3Submission.participant_type == "account",
        )
        .with_for_update()
    )
    if row is None:
        raise Top3NotFoundError("Current user's Top 3 submission not found")
    await db.execute(delete(Top3Submission).where(Top3Submission.id == row))
    await db.flush()
    await bump_data_revision(db)


async def get_viewer_assignment(
    db: AsyncSession, *, idea_id: str, viewer_user_id: int
) -> dict:
    revision = await get_data_revision(db)
    assignment_row = (
        await db.execute(
            select(Top3Assignment, Top3Concept)
            .join(Top3Concept, Top3Concept.id == Top3Assignment.concept_id)
            .where(Top3Assignment.idea_id == idea_id)
        )
    ).one_or_none()
    if assignment_row is None:
        return {"revision": revision, "assignment": None}
    assignment, concept = assignment_row

    submission_rows = (
        await db.execute(
            select(Top3Submission, User.username)
            .outerjoin(User, User.id == Top3Submission.account_user_id)
            .where(Top3Submission.assignment_idea_id == idea_id)
            .order_by(Top3Submission.created_at, Top3Submission.id)
        )
    ).all()
    revealed_ids = set(
        (
            await db.execute(
                select(Top3Reveal.submission_id).where(
                    Top3Reveal.viewer_user_id == viewer_user_id
                )
            )
        ).scalars()
    )
    active_users = list(
        (
            await db.execute(
                select(User).where(User.is_active.is_(True)).order_by(User.username)
            )
        ).scalars()
    )
    account_rows = {
        submission.account_user_id: (submission, username)
        for submission, username in submission_rows
        if submission.participant_type == "account"
    }
    contributors: list[dict] = []
    represented_user_ids: set[int] = set()
    for user in active_users:
        represented_user_ids.add(user.id)
        submission_pair = account_rows.get(user.id)
        if submission_pair is None:
            contributors.append(
                {
                    "submissionId": None,
                    "contributorType": "account",
                    "externalType": None,
                    "displayName": user.username,
                    "complete": False,
                    "isCurrentUser": user.id == viewer_user_id,
                    "revealed": False,
                }
            )
            continue
        submission, username = submission_pair
        contributors.append(
            serialize_top3_submission(
                submission,
                display_name=username or "Inactive account",
                current_user_id=viewer_user_id,
                revealed=submission.id in revealed_ids,
            )
        )

    # Preserve attribution for a now-inactive account. User deletion is
    # restricted while this row exists, so the username remains available.
    for user_id, (submission, username) in account_rows.items():
        if user_id in represented_user_ids:
            continue
        contributors.append(
            serialize_top3_submission(
                submission,
                display_name=username or "Inactive account",
                current_user_id=viewer_user_id,
                revealed=submission.id in revealed_ids,
            )
        )
    for submission, _username in submission_rows:
        if submission.participant_type != "external":
            continue
        contributors.append(
            serialize_top3_submission(
                submission,
                display_name=submission.external_display_name or "External contributor",
                current_user_id=viewer_user_id,
                revealed=False,
            )
        )

    return {
        "revision": revision,
        "assignment": {
            "ideaId": assignment.idea_id,
            "concept": serialize_top3_concept(concept),
            "assignedAt": assignment.assigned_at.isoformat(),
            "updatedAt": assignment.updated_at.isoformat(),
            "contributors": contributors,
        },
    }
