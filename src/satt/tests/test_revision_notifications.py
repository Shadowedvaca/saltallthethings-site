"""Revision notification authentication, commit, payload, and cleanup tests."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import os

import jwt
import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import satt.routes.sync as sync_routes
from satt.config import get_settings
from satt.crud import bump_data_revision
from satt.models import User


def _user(*, expired: bool = False) -> dict:
    expiry = datetime.now(timezone.utc) + timedelta(hours=-1 if expired else 1)
    return {"user_id": 901, "username": "sync-user", "exp": expiry.timestamp()}


class DisconnectSequence:
    def __init__(self, *states: bool):
        self.states = iter(states)

    async def is_disconnected(self) -> bool:
        return next(self.states, True)


@pytest.mark.asyncio
async def test_revision_event_is_minimal_and_disconnect_leaves_no_task(
    monkeypatch,
):
    async def committed_revision(_factory, _user_id):
        return 42

    monkeypatch.setattr(sync_routes, "_read_authorized_revision", committed_revision)
    before = asyncio.all_tasks()
    stream = sync_routes.revision_event_stream(
        DisconnectSequence(False, True),
        resource=sync_routes.CANONICAL_RESOURCE,
        after=41,
        user=_user(),
        factory=object(),
        poll_interval=0,
    )

    event = await anext(stream)
    assert event == (
        'id: canonical-state:42\nevent: revision\n'
        'data: {"resource":"canonical-state","revision":42}\n\n'
    )
    assert all(
        protected not in event
        for protected in (
            "pick",
            "proposal",
            "reveal",
            "username",
            "password",
            "database",
        )
    )
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert asyncio.all_tasks() == before


@pytest.mark.asyncio
async def test_stream_closes_when_account_is_revoked(monkeypatch):
    revisions = iter((7, None))

    async def authorization_sequence(_factory, _user_id):
        return next(revisions)

    monkeypatch.setattr(
        sync_routes, "_read_authorized_revision", authorization_sequence
    )
    stream = sync_routes.revision_event_stream(
        DisconnectSequence(False, False),
        resource=sync_routes.CANONICAL_RESOURCE,
        after=6,
        user=_user(),
        factory=object(),
        poll_interval=0,
    )
    assert "revision\":7" in await anext(stream)
    with pytest.raises(StopAsyncIteration):
        await anext(stream)


@pytest.mark.asyncio
async def test_idle_stream_emits_payload_free_heartbeat(monkeypatch):
    async def unchanged(_factory, _user_id):
        return 5

    monkeypatch.setattr(sync_routes, "_read_authorized_revision", unchanged)
    stream = sync_routes.revision_event_stream(
        DisconnectSequence(False),
        resource=sync_routes.CANONICAL_RESOURCE,
        after=5,
        user=_user(),
        factory=object(),
        poll_interval=0,
        heartbeat_interval=0,
    )
    assert await anext(stream) == ": keep-alive\n\n"
    await stream.aclose()


@pytest.mark.asyncio
async def test_expired_stream_ends_before_reading_activity(monkeypatch):
    async def must_not_read(*_args):
        pytest.fail("expired stream must not read canonical activity")

    monkeypatch.setattr(sync_routes, "_read_authorized_revision", must_not_read)
    stream = sync_routes.revision_event_stream(
        DisconnectSequence(False),
        resource=sync_routes.CANONICAL_RESOURCE,
        after=0,
        user=_user(expired=True),
        factory=object(),
        poll_interval=0,
    )
    with pytest.raises(StopAsyncIteration):
        await anext(stream)


@pytest.mark.asyncio
async def test_subscription_route_enforces_resource_and_active_account(monkeypatch):
    async def active_revision(_factory, _user_id):
        return 3

    monkeypatch.setattr(sync_routes, "_read_authorized_revision", active_revision)
    with pytest.raises(HTTPException) as unknown:
        await sync_routes.subscribe_to_revisions(
            DisconnectSequence(True), "top3-picks", 0, _user(), object()
        )
    assert unknown.value.status_code == 404

    async def revoked(_factory, _user_id):
        return None

    monkeypatch.setattr(sync_routes, "_read_authorized_revision", revoked)
    with pytest.raises(HTTPException) as inactive:
        await sync_routes.subscribe_to_revisions(
            DisconnectSequence(True),
            sync_routes.CANONICAL_RESOURCE,
            0,
            _user(),
            object(),
        )
    assert inactive.value.status_code == 401

    with pytest.raises(HTTPException) as expired:
        await sync_routes.subscribe_to_revisions(
            DisconnectSequence(True),
            sync_routes.CANONICAL_RESOURCE,
            0,
            _user(expired=True),
            object(),
        )
    assert expired.value.status_code == 401

    monkeypatch.setattr(sync_routes, "_read_authorized_revision", active_revision)
    response = await sync_routes.subscribe_to_revisions(
        DisconnectSequence(True),
        sync_routes.CANONICAL_RESOURCE,
        3,
        _user(),
        object(),
    )
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache, no-store"
    assert response.headers["x-accel-buffering"] == "no"
    with pytest.raises(StopAsyncIteration):
        await anext(response.body_iterator)


def test_token_lifetime_requires_valid_expiry():
    assert sync_routes._token_is_expired({})
    assert sync_routes._token_is_expired({"exp": "not-a-timestamp"})
    assert not sync_routes._token_is_expired(
        {"exp": datetime.now() + timedelta(minutes=1)}
    )


@pytest.mark.asyncio
async def test_subscription_http_rejects_missing_expired_and_unknown_resource(
    client: AsyncClient,
):
    missing = await client.get(
        "/api/sync/revisions?resource=canonical-state&after=0"
    )
    assert missing.status_code == 401

    settings = get_settings()
    expired_token = jwt.encode(
        {
            "user_id": 901,
            "username": "sync-user",
            "is_admin": False,
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    expired = await client.get(
        "/api/sync/revisions?resource=canonical-state&after=0",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert expired.status_code == 401

    valid_token = jwt.encode(
        {
            "user_id": 901,
            "username": "sync-user",
            "is_admin": False,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    unknown = await client.get(
        "/api/sync/revisions?resource=top3-picks&after=0",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    invalid_cursor = await client.get(
        "/api/sync/revisions?resource=canonical-state&after=-1",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert unknown.status_code == 404
    assert invalid_cursor.status_code == 422


@pytest.mark.asyncio
async def test_only_committed_revision_is_observable_and_sessions_close(test_schema):
    test_url = os.environ["TEST_DATABASE_URL"]
    engine = create_async_engine(test_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory.begin() as setup:
            setup.add(
                User(
                    id=901,
                    username="sync-user",
                    password_hash="unused",
                    is_active=True,
                )
            )

        baseline = await sync_routes._read_authorized_revision(factory, 901)
        assert baseline is not None

        writer = factory()
        await writer.begin()
        await bump_data_revision(writer)
        assert await sync_routes._read_authorized_revision(factory, 901) == baseline
        await writer.rollback()
        await writer.close()
        assert await sync_routes._read_authorized_revision(factory, 901) == baseline

        async with factory.begin() as committed:
            committed_revision = await bump_data_revision(committed)
        assert committed_revision == baseline + 1
        assert (
            await sync_routes._read_authorized_revision(factory, 901)
            == committed_revision
        )

        async with factory.begin() as revoke:
            user = await revoke.get(User, 901)
            assert user is not None
            user.is_active = False
        assert await sync_routes._read_authorized_revision(factory, 901) is None
    finally:
        await engine.dispose()
