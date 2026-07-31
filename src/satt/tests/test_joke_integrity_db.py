"""Database-backed joke assignment, deletion, and concurrency coverage."""

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
from satt.crud import assign_joke_to_idea
from satt.models import Idea, Joke


def _headers() -> dict:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "user_id": 1,
            "username": "testuser",
            "is_admin": False,
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


def _idea(idea_id: str) -> dict:
    return {
        "id": idea_id,
        "titles": [idea_id],
        "selectedTitle": idea_id,
        "summary": "",
        "outline": [],
        "status": "processed",
    }


def _joke(joke_id: str, text: str) -> dict:
    return {
        "id": joke_id,
        "text": text,
        "status": "unused",
        "source": "manual",
        "usedByIdeaId": None,
    }


@pytest.mark.asyncio
async def test_assignment_reassignment_and_free_survive_reload(
    db_client: AsyncClient,
):
    await db_client.put(
        "/api/data/ideas",
        json=[_idea("integrity-idea-1"), _idea("integrity-idea-2")],
        headers=_headers(),
    )
    await db_client.put(
        "/api/data/jokes",
        json=[
            _joke("integrity-joke-1", "First integrity joke"),
            _joke("integrity-joke-2", "Second integrity joke"),
        ],
        headers=_headers(),
    )

    first = await db_client.put(
        "/api/jokes/integrity-joke-1/assignment",
        json={"ideaId": "integrity-idea-1"},
        headers=_headers(),
    )
    assert first.status_code == 200

    replacement = await db_client.put(
        "/api/jokes/integrity-joke-2/assignment",
        json={"ideaId": "integrity-idea-1"},
        headers=_headers(),
    )
    assert replacement.status_code == 200
    reloaded = await db_client.get("/api/data/jokes", headers=_headers())
    by_id = {joke["id"]: joke for joke in reloaded.json()}
    assert by_id["integrity-joke-1"]["status"] == "unused"
    assert by_id["integrity-joke-1"]["usedByIdeaId"] is None
    assert by_id["integrity-joke-2"]["status"] == "used"
    assert by_id["integrity-joke-2"]["usedByIdeaId"] == "integrity-idea-1"

    moved = await db_client.put(
        "/api/jokes/integrity-joke-2/assignment",
        json={"ideaId": "integrity-idea-2"},
        headers=_headers(),
    )
    assert moved.status_code == 200
    freed = await db_client.delete(
        "/api/jokes/integrity-joke-2/assignment",
        headers=_headers(),
    )
    assert freed.status_code == 200
    [joke] = [
        joke
        for joke in freed.json()["data"]
        if joke["id"] == "integrity-joke-2"
    ]
    assert joke["status"] == "unused"
    assert joke["usedByIdeaId"] is None


@pytest.mark.asyncio
async def test_deleting_idea_atomically_frees_assigned_joke(
    db_client: AsyncClient,
):
    await db_client.put(
        "/api/data/ideas",
        json=[_idea("delete-integrity-idea")],
        headers=_headers(),
    )
    await db_client.put(
        "/api/data/jokes",
        json=[_joke("delete-integrity-joke", "Delete integrity joke")],
        headers=_headers(),
    )
    await db_client.put(
        "/api/jokes/delete-integrity-joke/assignment",
        json={"ideaId": "delete-integrity-idea"},
        headers=_headers(),
    )

    response = await db_client.delete(
        "/api/ideas/delete-integrity-idea",
        headers=_headers(),
    )
    assert response.status_code == 200
    assert response.json()["data"]["ideas"] == []
    [joke] = response.json()["data"]["jokes"]
    assert joke["status"] == "unused"
    assert joke["usedByIdeaId"] is None

    reloaded = await db_client.get("/api/export", headers=_headers())
    assert reloaded.json()["ideas"] == []
    assert reloaded.json()["jokes"][0]["usedByIdeaId"] is None


@pytest.mark.asyncio
async def test_full_idea_replace_also_frees_removed_ideas_joke(
    db_client: AsyncClient,
):
    await db_client.put(
        "/api/data/ideas",
        json=[_idea("replace-delete-idea")],
        headers=_headers(),
    )
    await db_client.put(
        "/api/data/jokes",
        json=[_joke("replace-delete-joke", "Replace delete joke")],
        headers=_headers(),
    )
    await db_client.put(
        "/api/jokes/replace-delete-joke/assignment",
        json={"ideaId": "replace-delete-idea"},
        headers=_headers(),
    )
    removed = await db_client.put(
        "/api/data/ideas",
        json=[],
        headers=_headers(),
    )
    assert removed.status_code == 200
    jokes = await db_client.get("/api/data/jokes", headers=_headers())
    assert jokes.json()[0]["status"] == "unused"
    assert jokes.json()[0]["usedByIdeaId"] is None


@pytest.mark.asyncio
async def test_atomic_lifecycle_routes_reject_missing_resources(
    db_client: AsyncClient,
):
    missing_joke = await db_client.put(
        "/api/jokes/missing/assignment",
        json={"ideaId": "missing"},
        headers=_headers(),
    )
    missing_idea = await db_client.delete(
        "/api/ideas/missing",
        headers=_headers(),
    )
    assert missing_joke.status_code == 404
    assert missing_idea.status_code == 404


@pytest.mark.asyncio
async def test_full_bank_write_rejects_duplicate_text_and_assignments(
    db_client: AsyncClient,
):
    duplicate_text = await db_client.put(
        "/api/data/jokes",
        json=[
            _joke("duplicate-one", "Same—joke!"),
            _joke("duplicate-two", " same joke "),
        ],
        headers=_headers(),
    )
    assert duplicate_text.status_code == 422
    assert "duplicates another banked joke" in duplicate_text.json()["detail"]

    await db_client.put(
        "/api/data/ideas",
        json=[_idea("duplicate-assignment-idea")],
        headers=_headers(),
    )
    duplicate_assignment = await db_client.put(
        "/api/data/jokes",
        json=[
            {
                **_joke("assignment-one", "Assignment one"),
                "status": "used",
                "usedByIdeaId": "duplicate-assignment-idea",
            },
            {
                **_joke("assignment-two", "Assignment two"),
                "status": "used",
                "usedByIdeaId": "duplicate-assignment-idea",
            },
        ],
        headers=_headers(),
    )
    assert duplicate_assignment.status_code == 422
    assert "only one used joke" in duplicate_assignment.json()["detail"]


@pytest.mark.asyncio
async def test_database_unique_constraint_rejects_two_jokes_for_one_idea(
    db_session: AsyncSession,
):
    db_session.add(Idea(id="constraint-idea"))
    db_session.add_all(
        [
            Joke(
                id="constraint-joke-1",
                text="Constraint one",
                status="used",
                used_by_idea_id="constraint-idea",
            ),
            Joke(
                id="constraint-joke-2",
                text="Constraint two",
                status="used",
                used_by_idea_id="constraint-idea",
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_concurrent_assignments_leave_exactly_one_joke_on_idea(
    db_session: AsyncSession,
):
    idea_id = "concurrent-integrity-idea"
    joke_ids = ["concurrent-integrity-joke-1", "concurrent-integrity-joke-2"]
    db_session.add(Idea(id=idea_id))
    db_session.add_all(
        [
            Joke(id=joke_ids[0], text="Concurrent one", status="unused"),
            Joke(id=joke_ids[1], text="Concurrent two", status="unused"),
        ]
    )
    await db_session.commit()

    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def assign(joke_id: str) -> None:
        async with factory() as session:
            await assign_joke_to_idea(session, joke_id, idea_id)
            await session.commit()

    try:
        await asyncio.gather(*(assign(joke_id) for joke_id in joke_ids))
        async with factory() as verify:
            result = await verify.execute(
                select(Joke).where(Joke.id.in_(joke_ids))
            )
            jokes = list(result.scalars())
            assigned = [joke for joke in jokes if joke.used_by_idea_id == idea_id]
            assert len(assigned) == 1
            assert assigned[0].status == "used"
            assert all(
                joke.status == "unused"
                for joke in jokes
                if joke.used_by_idea_id is None
            )
    finally:
        async with factory() as cleanup:
            await cleanup.execute(
                update(Joke)
                .where(Joke.id.in_(joke_ids))
                .values(status="unused", used_by_idea_id=None)
            )
            await cleanup.execute(delete(Joke).where(Joke.id.in_(joke_ids)))
            await cleanup.execute(delete(Idea).where(Idea.id == idea_id))
            await cleanup.commit()
