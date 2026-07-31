"""Construct private database URLs from server-side environment fields."""

from __future__ import annotations

import os
from urllib.parse import quote


PRIVATE_DATABASE_VARIABLES = (
    "SATT_DB_HOST",
    "SATT_DB_PORT",
    "SATT_DB_NAME",
    "SATT_DB_USER",
    "SATT_DB_PASSWORD",
)


def private_database_url_from_environment() -> str:
    """Build an encoded private URL without logging its component values."""

    values = {name: os.environ.get(name, "") for name in PRIVATE_DATABASE_VARIABLES}
    if any(not value for value in values.values()):
        raise RuntimeError("private database configuration is incomplete")

    return "postgresql+asyncpg://{}:{}@{}:{}/{}".format(
        quote(values["SATT_DB_USER"], safe=""),
        quote(values["SATT_DB_PASSWORD"], safe=""),
        values["SATT_DB_HOST"],
        values["SATT_DB_PORT"],
        quote(values["SATT_DB_NAME"], safe=""),
    )


def configure_database_url(*, require_private: bool = False) -> str:
    """Return DATABASE_URL or configure it from private server-side fields."""

    database_url = os.environ.get("DATABASE_URL", "")
    if database_url:
        return database_url

    has_private_configuration = any(
        os.environ.get(name, "") for name in PRIVATE_DATABASE_VARIABLES
    )
    if not has_private_configuration and not require_private:
        return ""

    database_url = private_database_url_from_environment()
    os.environ["DATABASE_URL"] = database_url
    return database_url
