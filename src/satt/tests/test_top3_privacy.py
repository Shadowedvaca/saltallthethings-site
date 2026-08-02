"""Top 3 ownership, redaction, lifecycle, constraints, and leakage tests."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from satt.config import get_settings
from satt.models import (
    Idea,
    Top3Assignment,
    Top3Concept,
    Top3Reveal,
    Top3Submission,
    User,
)
from satt.top3_crud import Top3ConflictError, save_current_submission


def _headers(user_id: int, username: str, *, admin: bool = False) -> dict[str, str]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "user_id": user_id,
            "username": username,
            "is_admin": admin,
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


async def _users(db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            User(id=101, username="rocket", password_hash="unused", is_admin=True),
            User(id=102, username="trog", password_hash="unused"),
            User(id=103, username="observer", password_hash="unused"),
        ]
    )
    await db_session.flush()


def _idea(idea_id: str) -> dict:
    return {
        "id": idea_id,
        "titles": ["Top 3 test"],
        "selectedTitle": "Top 3 test",
        "summary": "Private list test",
        "outline": [],
        "status": "processed",
    }


def _concept(concept_id: str = "top3-concept") -> dict:
    return {
        "id": concept_id,
        "name": "Best dungeon snacks",
        "description": "Rank snacks for a long dungeon.",
        "rules": "No conjured food.",
        "hostNotes": "Keep the reasoning surprising.",
        "aiExample": ["Cheese", "Jerky", "Fruit"],
        "status": "active",
        "source": "manual",
    }


async def _assigned(db_client: AsyncClient, db_session: AsyncSession) -> None:
    await _users(db_session)
    assert (
        await db_client.put(
            "/api/data/ideas", json=[_idea("top3-idea")], headers=_headers(101, "rocket")
        )
    ).status_code == 200
    assert (
        await db_client.post(
            "/api/top3/concepts", json=_concept(), headers=_headers(101, "rocket")
        )
    ).status_code == 201
    assert (
        await db_client.put(
            "/api/top3/episodes/top3-idea/assignment",
            json={"conceptId": "top3-concept"},
            headers=_headers(101, "rocket"),
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_top3_routes_require_authentication(client: AsyncClient):
    assert (await client.get("/api/top3/concepts")).status_code == 401
    assert (await client.get("/api/top3/episodes/idea")).status_code == 401
    assert (
        await client.put(
            "/api/top3/episodes/idea/submission",
            json={"id": "x", "picks": ["a", "b", "c"]},
        )
    ).status_code == 401


@pytest.mark.asyncio
async def test_ai_concept_provenance_round_trips_without_creating_a_submission(
    db_client: AsyncClient, db_session: AsyncSession
):
    await _users(db_session)
    generated_at = "2026-08-01T12:30:00Z"
    response = await db_client.post(
        "/api/top3/concepts",
        json={
            **_concept("ai-generated-concept"),
            "source": "ai",
            "aiProvider": "claude",
            "aiModelId": "claude-test-model",
            "aiGeneratedAt": generated_at,
        },
        headers=_headers(101, "rocket"),
    )
    assert response.status_code == 201
    saved = response.json()["concept"]
    assert saved["aiProvider"] == "claude"
    assert saved["aiModelId"] == "claude-test-model"
    assert datetime.fromisoformat(
        saved["aiGeneratedAt"].replace("Z", "+00:00")
    ) == datetime.fromisoformat(generated_at.replace("Z", "+00:00"))

    reloaded = await db_client.get(
        "/api/top3/concepts", headers=_headers(101, "rocket")
    )
    concept = next(
        item
        for item in reloaded.json()["concepts"]
        if item["id"] == "ai-generated-concept"
    )
    assert datetime.fromisoformat(
        concept["aiGeneratedAt"].replace("Z", "+00:00")
    ) == datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    submissions = await db_session.execute(select(Top3Submission))
    assert submissions.scalars().all() == []


@pytest.mark.asyncio
async def test_viewer_projection_redacts_other_accounts_even_for_admin(
    db_client: AsyncClient, db_session: AsyncSession
):
    await _assigned(db_client, db_session)
    rocket_secret = "rocket-secret-pick"
    saved = await db_client.put(
        "/api/top3/episodes/top3-idea/submission",
        json={
            "id": "rocket-submission",
            "picks": [rocket_secret, "Rocket Two", "Rocket Three"],
            "privateDiscussionNotes": "rocket-private-notes",
        },
        headers=_headers(101, "rocket"),
    )
    assert saved.status_code == 200
    own = saved.json()["assignment"]["contributors"]
    rocket = next(item for item in own if item["displayName"] == "rocket")
    assert rocket["picks"][0] == rocket_secret
    assert rocket["privateDiscussionNotes"] == "rocket-private-notes"

    for viewer in (_headers(102, "trog"), _headers(103, "observer", admin=True)):
        response = await db_client.get(
            "/api/top3/episodes/top3-idea", headers=viewer
        )
        assert response.status_code == 200
        assert rocket_secret not in response.text
        assert "rocket-private-notes" not in response.text
        rocket = next(
            item
            for item in response.json()["assignment"]["contributors"]
            if item["displayName"] == "rocket"
        )
        assert rocket == {
            "submissionId": "rocket-submission",
            "contributorType": "account",
            "externalType": None,
            "displayName": "rocket",
            "complete": True,
            "isCurrentUser": False,
            "revealed": False,
        }

    incomplete = next(
        item
        for item in saved.json()["assignment"]["contributors"]
        if item["displayName"] == "trog"
    )
    assert incomplete["complete"] is False
    assert "picks" not in incomplete


@pytest.mark.asyncio
async def test_reveal_is_viewer_specific_and_external_results_are_shared(
    db_client: AsyncClient, db_session: AsyncSession
):
    await _assigned(db_client, db_session)
    await db_client.put(
        "/api/top3/episodes/top3-idea/submission",
        json={
            "id": "rocket-submission",
            "picks": ["Rocket One", "Rocket Two", "Rocket Three"],
            "privateDiscussionNotes": "revealed notes",
        },
        headers=_headers(101, "rocket"),
    )
    db_session.add(
        Top3Submission(
            id="guest-submission",
            assignment_idea_id="top3-idea",
            participant_type="external",
            external_display_name="Guest One",
            external_type="guest",
            entered_by_user_id=101,
            pick_1="Guest Pick One",
            pick_2="Guest Pick Two",
            pick_3="Guest Pick Three",
            private_discussion_notes="shared guest notes",
        )
    )
    db_session.add(Top3Reveal(viewer_user_id=102, submission_id="rocket-submission"))
    await db_session.flush()

    trog = await db_client.get(
        "/api/top3/episodes/top3-idea", headers=_headers(102, "trog")
    )
    observer = await db_client.get(
        "/api/top3/episodes/top3-idea", headers=_headers(103, "observer")
    )
    assert "Rocket One" in trog.text
    assert "revealed notes" in trog.text
    assert "Rocket One" not in observer.text
    assert "revealed notes" not in observer.text
    assert "Guest Pick One" in trog.text and "Guest Pick One" in observer.text


@pytest.mark.asyncio
async def test_general_export_import_and_cache_contract_never_include_top3_picks(
    db_client: AsyncClient, db_session: AsyncSession
):
    await _assigned(db_client, db_session)
    await db_client.put(
        "/api/top3/episodes/top3-idea/submission",
        json={
            "id": "private-export-submission",
            "picks": ["never-export-one", "never-export-two", "never-export-three"],
            "privateDiscussionNotes": "never-export-notes",
        },
        headers=_headers(101, "rocket"),
    )
    exported = await db_client.get("/api/export", headers=_headers(101, "rocket"))
    assert exported.status_code == 200
    assert not any(key.lower().startswith("top3") for key in exported.json())
    assert "never-export" not in exported.text

    rejected = await db_client.put(
        "/api/import",
        json={"top3Submissions": [{"picks": ["stolen", "data", "here"]}]},
        headers=_headers(101, "rocket"),
    )
    assert rejected.status_code == 422
    assert "top3Submissions" in rejected.json()["detail"]


@pytest.mark.asyncio
async def test_submission_contract_cannot_spoof_owner_or_write_another_object(
    db_client: AsyncClient, db_session: AsyncSession
):
    await _assigned(db_client, db_session)
    spoof = await db_client.put(
        "/api/top3/episodes/top3-idea/submission",
        json={
            "id": "spoof",
            "picks": ["One", "Two", "Three"],
            "accountUserId": 101,
        },
        headers=_headers(102, "trog"),
    )
    assert spoof.status_code == 422

    saved = await db_client.put(
        "/api/top3/episodes/top3-idea/submission",
        json={"id": "trog-list", "picks": ["One", "Two", "Three"]},
        headers=_headers(102, "trog"),
    )
    assert saved.status_code == 200
    renamed = await db_client.put(
        "/api/top3/episodes/top3-idea/submission",
        json={"id": "different-id", "picks": ["Four", "Five", "Six"]},
        headers=_headers(102, "trog"),
    )
    assert renamed.status_code == 409
    assert "original id" in renamed.json()["detail"]


@pytest.mark.asyncio
async def test_database_constraints_reject_duplicate_owner_and_invalid_picks(
    db_session: AsyncSession,
):
    await _users(db_session)
    db_session.add(Idea(id="constraint-idea"))
    db_session.add(
        Top3Concept(
            id="constraint-concept",
            name="Constraint",
            description="Constraint test",
            created_by_user_id=101,
        )
    )
    db_session.add(
        Top3Assignment(
            idea_id="constraint-idea",
            concept_id="constraint-concept",
            assigned_by_user_id=101,
        )
    )
    await db_session.flush()
    db_session.add_all(
        [
            Top3Submission(
                id="duplicate-one",
                assignment_idea_id="constraint-idea",
                participant_type="account",
                account_user_id=101,
                pick_1="One",
                pick_2="Two",
                pick_3="Three",
            ),
            Top3Submission(
                id="duplicate-two",
                assignment_idea_id="constraint-idea",
                participant_type="account",
                account_user_id=101,
                pick_1="Four",
                pick_2="Five",
                pick_3="Six",
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_database_rejects_duplicate_picks_and_user_deletion_with_audit_rows(
    db_session: AsyncSession,
):
    await _users(db_session)
    db_session.add(Idea(id="constraint-picks-idea"))
    db_session.add(
        Top3Concept(
            id="constraint-picks-concept",
            name="Constraint",
            description="Constraint test",
            created_by_user_id=101,
        )
    )
    db_session.add(
        Top3Assignment(
            idea_id="constraint-picks-idea",
            concept_id="constraint-picks-concept",
            assigned_by_user_id=101,
        )
    )
    await db_session.flush()
    db_session.add(
        Top3Submission(
            id="duplicate-picks",
            assignment_idea_id="constraint-picks-idea",
            participant_type="account",
            account_user_id=101,
            pick_1="Same",
            pick_2="same",
            pick_3="Different",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()

    await _users(db_session)
    db_session.add(
        Top3Concept(
            id="user-audit-concept",
            name="Audit",
            description="Preserve authorship",
            created_by_user_id=101,
        )
    )
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(delete(User).where(User.id == 101))
    await db_session.rollback()


@pytest.mark.asyncio
async def test_assigned_concept_cannot_be_deleted(
    db_client: AsyncClient, db_session: AsyncSession
):
    await _assigned(db_client, db_session)
    response = await db_client.delete(
        "/api/top3/concepts/top3-concept", headers=_headers(101, "rocket")
    )
    assert response.status_code == 409
    assert "Assigned" in response.json()["detail"]


@pytest.mark.asyncio
async def test_concept_bank_lists_assignment_state_without_participant_picks(
    db_client: AsyncClient, db_session: AsyncSession
):
    await _assigned(db_client, db_session)
    response = await db_client.get(
        "/api/top3/concepts", headers=_headers(101, "rocket")
    )
    assert response.status_code == 200
    concept = next(
        item for item in response.json()["concepts"] if item["id"] == "top3-concept"
    )
    assert concept["assignedEpisodes"] == [
        {
            "ideaId": "top3-idea",
            "title": "Top 3 test",
            "episodeNumber": None,
        }
    ]
    assert "picks" not in response.text
    assert "privateDiscussionNotes" not in response.text


@pytest.mark.asyncio
async def test_reassignment_and_idea_deletion_cascade_private_rows(
    db_client: AsyncClient, db_session: AsyncSession
):
    await _assigned(db_client, db_session)
    await db_client.post(
        "/api/top3/concepts",
        json=_concept("replacement-concept"),
        headers=_headers(101, "rocket"),
    )
    await db_client.put(
        "/api/top3/episodes/top3-idea/submission",
        json={"id": "cascade-list", "picks": ["One", "Two", "Three"]},
        headers=_headers(101, "rocket"),
    )
    db_session.add(Top3Reveal(viewer_user_id=102, submission_id="cascade-list"))
    await db_session.flush()

    replaced = await db_client.put(
        "/api/top3/episodes/top3-idea/assignment",
        json={"conceptId": "replacement-concept"},
        headers=_headers(101, "rocket"),
    )
    assert replaced.status_code == 200
    assert all(
        not contributor["complete"]
        for contributor in replaced.json()["assignment"]["contributors"]
        if contributor["contributorType"] == "account"
    )
    assert await db_session.scalar(select(Top3Reveal.submission_id)) is None

    await db_client.put(
        "/api/top3/episodes/top3-idea/submission",
        json={"id": "delete-cascade-list", "picks": ["A", "B", "C"]},
        headers=_headers(101, "rocket"),
    )
    deleted = await db_client.delete(
        "/api/ideas/top3-idea", headers=_headers(101, "rocket")
    )
    assert deleted.status_code == 200
    assert await db_session.scalar(select(Top3Assignment.idea_id)) is None
    assert await db_session.scalar(select(Top3Submission.id)) is None


@pytest.mark.asyncio
async def test_concurrent_first_submissions_preserve_one_owner_row(
    db_session: AsyncSession,
):
    await _users(db_session)
    db_session.add(Idea(id="concurrent-top3-idea"))
    db_session.add(
        Top3Concept(
            id="concurrent-top3-concept",
            name="Concurrent",
            description="Concurrent test",
            created_by_user_id=101,
        )
    )
    db_session.add(
        Top3Assignment(
            idea_id="concurrent-top3-idea",
            concept_id="concurrent-top3-concept",
            assigned_by_user_id=101,
        )
    )
    await db_session.commit()
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def save(submission_id: str):
        async with factory() as session:
            try:
                await save_current_submission(
                    session,
                    idea_id="concurrent-top3-idea",
                    user_id=101,
                    submission={
                        "id": submission_id,
                        "picks": [submission_id, "Two", "Three"],
                        "privateDiscussionNotes": "",
                    },
                )
                await session.commit()
                return "saved"
            except Top3ConflictError:
                await session.rollback()
                return "conflict"

    try:
        results = await asyncio.gather(save("concurrent-a"), save("concurrent-b"))
        assert sorted(results) == ["conflict", "saved"]
        async with factory() as verify:
            rows = list(
                (
                    await verify.execute(
                        select(Top3Submission).where(
                            Top3Submission.assignment_idea_id == "concurrent-top3-idea",
                            Top3Submission.account_user_id == 101,
                        )
                    )
                ).scalars()
            )
            assert len(rows) == 1
    finally:
        async with factory() as cleanup:
            await cleanup.execute(
                delete(Top3Assignment).where(
                    Top3Assignment.idea_id == "concurrent-top3-idea"
                )
            )
            await cleanup.execute(
                delete(Top3Concept).where(Top3Concept.id == "concurrent-top3-concept")
            )
            await cleanup.execute(delete(Idea).where(Idea.id == "concurrent-top3-idea"))
            await cleanup.execute(delete(User).where(User.id.in_([101, 102, 103])))
            await cleanup.commit()
