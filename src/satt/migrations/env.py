"""Alembic environment configuration for SATT."""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import async_engine_from_config

# Load .env from project root
load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

# Ensure src/ is on path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from satt.database_url import configure_database_url  # noqa: E402
from satt.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Normal container startup exports DATABASE_URL inside the entrypoint process.
# Later docker compose exec processes intentionally receive only the private
# SATT_DB_* fields, so Alembic must reconstruct the same URL itself.
database_url = configure_database_url(require_private=True)
config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema="satt",
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    # Alembic creates its version table before running revision 0001. Ensure the
    # namespace exists on a completely fresh database so that version tracking
    # can be created inside the application schema.
    connection.execute(text("CREATE SCHEMA IF NOT EXISTS satt"))
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        version_table_schema="satt",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.begin() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
