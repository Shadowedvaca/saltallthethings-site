"""Transactional Top 3 persistence and viewer-scoped privacy projection."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from satt.crud import bump_data_revision, get_data_revision
from satt.models import (
    Assignment as ScheduleAssignment,
    Idea,
    ShowSlot,
    Top3Assignment,
    Top3Concept,
    Top3Reveal,
    Top3Submission,
    User,
)
from satt.episode_numbers import effective_episode_number
from satt.serializers import serialize_top3_concept, serialize_top3_submission

_TOP3_LIFECYCLE_LOCK_ID = 0x53415433


class Top3NotFoundError(LookupError):
    pass


class Top3ConflictError(RuntimeError):
    pass


def _account_display_name(username: str | None) -> str:
    value = username or "Inactive account"
    return value[:1].upper() + value[1:]


async def _lock_top3_lifecycle(db: AsyncSession) -> None:
    await db.execute(select(func.pg_advisory_xact_lock(_TOP3_LIFECYCLE_LOCK_ID)))


async def list_concepts(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Top3Concept).order_by(Top3Concept.created_at, Top3Concept.id)
    )
    concepts = [serialize_top3_concept(row) for row in result.scalars()]
    assignment_result = await db.execute(
        select(
            Top3Assignment.concept_id,
            Idea.id,
            Idea.selected_title,
            Idea.titles,
            ShowSlot.episode_number,
            ShowSlot.episode_num,
            ShowSlot.episode_number_override,
        )
        .join(Idea, Idea.id == Top3Assignment.idea_id)
        .outerjoin(ScheduleAssignment, ScheduleAssignment.idea_id == Idea.id)
        .outerjoin(ShowSlot, ShowSlot.id == ScheduleAssignment.slot_id)
        .order_by(ShowSlot.episode_num.nulls_last(), Idea.id)
    )
    assignments_by_concept: dict[str, list[dict]] = {}
    for (
        concept_id,
        idea_id,
        selected_title,
        titles,
        episode_number,
        episode_num,
        episode_number_override,
    ) in assignment_result:
        fallback_title = next(
            (title for title in (titles or []) if isinstance(title, str) and title.strip()),
            None,
        )
        assignments_by_concept.setdefault(concept_id, []).append(
            {
                "ideaId": idea_id,
                "title": selected_title or fallback_title or "Untitled episode idea",
                "episodeNumber": (
                    effective_episode_number(
                        episode_number,
                        episode_num,
                        episode_number_override,
                    )
                    if episode_number is not None
                    else None
                ),
            }
        )
    for concept in concepts:
        concept["assignedEpisodes"] = assignments_by_concept.get(concept["id"], [])
    return concepts


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


async def reveal_submission(
    db: AsyncSession, *, idea_id: str, submission_id: str, viewer_user_id: int
) -> None:
    await _lock_top3_lifecycle(db)
    submission = await db.scalar(
        select(Top3Submission)
        .where(
            Top3Submission.id == submission_id,
            Top3Submission.assignment_idea_id == idea_id,
        )
        .with_for_update()
    )
    if submission is None:
        raise Top3NotFoundError("Top 3 submission not found for this episode")
    if submission.participant_type != "account":
        raise Top3ConflictError("External Top 3 results are already shared")
    if submission.account_user_id == viewer_user_id:
        raise Top3ConflictError("A user cannot reveal their own Top 3 submission")
    result = await db.execute(
        insert(Top3Reveal)
        .values(viewer_user_id=viewer_user_id, submission_id=submission_id)
        .on_conflict_do_nothing(
            index_elements=[Top3Reveal.viewer_user_id, Top3Reveal.submission_id]
        )
    )
    await db.flush()
    if result.rowcount:
        await bump_data_revision(db)


async def create_external_submission(
    db: AsyncSession, *, idea_id: str, user_id: int, submission: dict
) -> None:
    await _lock_top3_lifecycle(db)
    assignment = await db.scalar(
        select(Top3Assignment.idea_id)
        .where(Top3Assignment.idea_id == idea_id)
        .with_for_update()
    )
    if assignment is None:
        raise Top3NotFoundError("Top 3 assignment not found")
    duplicate = await db.scalar(
        select(Top3Submission.id).where(Top3Submission.id == submission["id"])
    )
    if duplicate is not None:
        raise Top3ConflictError("Top 3 submission id already exists")
    db.add(
        Top3Submission(
            id=submission["id"],
            assignment_idea_id=idea_id,
            participant_type="external",
            external_display_name=submission["displayName"],
            external_type=submission["externalType"],
            entered_by_user_id=user_id,
            pick_1=submission["picks"][0],
            pick_2=submission["picks"][1],
            pick_3=submission["picks"][2],
            private_discussion_notes=submission["privateDiscussionNotes"],
        )
    )
    await db.flush()
    await bump_data_revision(db)


async def update_external_submission(
    db: AsyncSession, *, idea_id: str, submission: dict
) -> None:
    await _lock_top3_lifecycle(db)
    row = await db.scalar(
        select(Top3Submission)
        .where(
            Top3Submission.id == submission["id"],
            Top3Submission.assignment_idea_id == idea_id,
            Top3Submission.participant_type == "external",
        )
        .with_for_update()
    )
    if row is None:
        raise Top3NotFoundError("External Top 3 submission not found")
    row.external_display_name = submission["displayName"]
    row.external_type = submission["externalType"]
    row.pick_1, row.pick_2, row.pick_3 = submission["picks"]
    row.private_discussion_notes = submission["privateDiscussionNotes"]
    row.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await bump_data_revision(db)


async def delete_external_submission(
    db: AsyncSession, *, idea_id: str, submission_id: str
) -> None:
    await _lock_top3_lifecycle(db)
    row = await db.scalar(
        select(Top3Submission)
        .where(
            Top3Submission.id == submission_id,
            Top3Submission.assignment_idea_id == idea_id,
            Top3Submission.participant_type == "external",
        )
        .with_for_update()
    )
    if row is None:
        raise Top3NotFoundError("External Top 3 submission not found")
    await db.delete(row)
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
    revealed_at_by_id = dict(
        (
            await db.execute(
                select(Top3Reveal.submission_id, Top3Reveal.revealed_at)
                .join(Top3Submission, Top3Submission.id == Top3Reveal.submission_id)
                .where(
                    Top3Reveal.viewer_user_id == viewer_user_id,
                    Top3Submission.assignment_idea_id == idea_id,
                )
            )
        ).all()
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
                    "displayName": _account_display_name(user.username),
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
                display_name=_account_display_name(username),
                current_user_id=viewer_user_id,
                revealed_at=revealed_at_by_id.get(submission.id),
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
                display_name=_account_display_name(username),
                current_user_id=viewer_user_id,
                revealed_at=revealed_at_by_id.get(submission.id),
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
                revealed_at=None,
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


async def get_spotify_results(
    db: AsyncSession, *, idea_id: str, viewer_user_id: int
) -> dict | None:
    """Return the viewer-authorized, read-only publication projection."""
    assignment_row = (
        await db.execute(
            select(Top3Assignment, Top3Concept)
            .join(Top3Concept, Top3Concept.id == Top3Assignment.concept_id)
            .where(Top3Assignment.idea_id == idea_id)
        )
    ).one_or_none()
    if assignment_row is None:
        return None
    _assignment, concept = assignment_row
    rows = (
        await db.execute(
            select(Top3Submission, User.username)
            .outerjoin(User, User.id == Top3Submission.account_user_id)
            .where(Top3Submission.assignment_idea_id == idea_id)
        )
    ).all()
    revealed_submission_ids = set(
        (
            await db.execute(
                select(Top3Reveal.submission_id)
                .join(
                    Top3Submission,
                    Top3Submission.id == Top3Reveal.submission_id,
                )
                .where(
                    Top3Reveal.viewer_user_id == viewer_user_id,
                    Top3Submission.assignment_idea_id == idea_id,
                )
            )
        ).scalars()
    )
    ordered_contributors = []
    for submission, username in rows:
        if (
            submission.participant_type == "account"
            and submission.account_user_id != viewer_user_id
            and submission.id not in revealed_submission_ids
        ):
            continue
        display_name = (
            _account_display_name(username)
            if submission.participant_type == "account"
            else submission.external_display_name or "External contributor"
        )
        picks = [submission.pick_1, submission.pick_2, submission.pick_3]
        ordered_contributors.append(
            (
                (
                    0 if submission.participant_type == "account" else 1,
                    display_name.casefold(),
                    display_name,
                    tuple(pick.casefold() for pick in picks),
                    tuple(picks),
                ),
                {"displayName": display_name, "picks": picks},
            )
        )
    ordered_contributors.sort(key=lambda item: item[0])
    return {
        "listName": concept.name,
        "contributors": [item[1] for item in ordered_contributors],
    }
