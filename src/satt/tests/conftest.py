"""Test configuration and shared fixtures for SATT tests.

DB-requiring tests use the `db_session` and `db_client` fixtures, which
connect to a Postgres instance at TEST_DATABASE_URL (or the default sattdb).

Tests that don't need a DB (e.g. health) use the plain `client` fixture.
"""

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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

_test_engine = None
_test_factory = None


def get_test_engine():
    global _test_engine
    if _test_engine is None:
        _test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    return _test_engine


def get_test_factory():
    global _test_factory
    if _test_factory is None:
        _test_factory = async_sessionmaker(get_test_engine(), expire_on_commit=False)
    return _test_factory


@pytest_asyncio.fixture(scope="session")
async def test_schema():
    """Create satt schema and tables in the test DB. Session-scoped."""
    engine = get_test_engine()
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
    """Yield a DB session that rolls back after each test."""
    factory = get_test_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()


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
