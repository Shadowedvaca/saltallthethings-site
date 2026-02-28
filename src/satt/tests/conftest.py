"""Test configuration and shared fixtures for SATT tests.

DB-requiring tests use the `db_session` and `db_client` fixtures, which
connect to a Postgres instance at TEST_DATABASE_URL (or the default sattdb).

Tests that don't need a DB (e.g. health) use the plain `client` fixture.

NullPool is used for the test engine so that asyncpg connections are never
cached in a pool. Each DB operation opens a fresh connection in the current
event loop, which prevents "Future attached to a different loop" errors when
the session-scoped schema fixture and function-scoped test fixtures run in
different event loop contexts.
"""

import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from satt.config import get_settings
from satt.database import get_db
from satt.main import app
from satt.models import Base

# ---------------------------------------------------------------------------
# Simple client (no DB override — for endpoints that don't touch the DB)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient for endpoints that don't require a real DB connection."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# DB-backed client (requires Postgres at TEST_DATABASE_URL)
# ---------------------------------------------------------------------------

_settings = get_settings()
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    _settings.database_url,
)


def _make_engine():
    """Create a NullPool async engine. NullPool means no connection reuse,
    so every execute() opens a fresh asyncpg connection in the current event
    loop — safe across session- and function-scoped fixtures."""
    return create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)


@pytest_asyncio.fixture(scope="session")
async def test_schema():
    """Create satt schema and tables in the test DB. Session-scoped."""
    engine = _make_engine()
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS satt"))
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP SCHEMA IF EXISTS satt CASCADE"))
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_schema) -> AsyncGenerator[AsyncSession, None]:
    """Yield a DB session per test.

    Data written in the test is flushed but never committed, so it is
    invisible to all other sessions. Best-effort rollback + dispose on
    teardown; swallow errors that occur when the cleanup event loop
    differs from the connection's origin loop (NullPool teardown quirk).
    """
    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        try:
            await session.rollback()
        except Exception:
            pass
        try:
            await session.close()
        except Exception:
            pass
        try:
            await engine.dispose()
        except Exception:
            pass


@pytest_asyncio.fixture
async def db_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient wired to the test DB session."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
