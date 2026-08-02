"""Fingerprint stable SATT production data without emitting record contents."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import os
from typing import Any
from urllib.parse import quote

from sqlalchemy import text

from satt.config import get_settings
from satt.database import get_engine


AUTH_QUERIES = {
    "users": """
        SELECT id, username, password_hash, is_admin, is_active, created_at
        FROM satt.users ORDER BY id
    """,
    "invite_codes": """
        SELECT code, created_by_user_id, used_at, expires_at
        FROM satt.invite_codes ORDER BY code
    """,
}
DATA_QUERIES = {
    "config": """
        SELECT id, data, updated_at
        FROM satt.config ORDER BY id
    """,
    "ideas": """
        SELECT id, titles, selected_title, summary, outline, status,
               image_file_id, raw_notes, created_at, updated_at
        FROM satt.ideas ORDER BY id
    """,
    # Revision 0005 intentionally normalizes status. The remaining columns
    # prove that joke content and assignments survive that migration.
    "jokes": """
        SELECT id, text, source, used_by_idea_id, created_at
        FROM satt.jokes ORDER BY id
    """,
    "show_slots": """
        SELECT id, episode_number, episode_num, record_date, release_date,
               is_rollout, release_date_override, production_file_key,
               asset_inventory, transcription_job
        FROM satt.show_slots ORDER BY id
    """,
    "assignments": """
        SELECT slot_id, idea_id, assigned_at
        FROM satt.assignments ORDER BY slot_id
    """,
}
OPTIONAL_DATA_QUERIES = {
    # Additive release tables are represented as an empty collection before
    # their migration and queried normally afterward. This keeps cutover
    # continuity comparable across the migration boundary without weakening
    # checks once the table contains data.
    "songs": """
        SELECT id, artist, title, youtube_url, private_notes, status,
               assigned_idea_id, created_at, updated_at
        FROM satt.songs ORDER BY id
    """,
    "top3_concepts": """
        SELECT id, name, description, rules, host_notes, ai_example, status,
               source, ai_provider, ai_model_id, ai_generated_at,
               created_by_user_id, created_at, updated_at
        FROM satt.top3_concepts ORDER BY id
    """,
    "top3_assignments": """
        SELECT idea_id, concept_id, assigned_by_user_id, assigned_at, updated_at
        FROM satt.top3_assignments ORDER BY idea_id
    """,
    "top3_submissions": """
        SELECT id, assignment_idea_id, participant_type, account_user_id,
               external_display_name, external_type, entered_by_user_id,
               pick_1, pick_2, pick_3, private_discussion_notes,
               created_at, updated_at
        FROM satt.top3_submissions ORDER BY id
    """,
    "top3_reveals": """
        SELECT viewer_user_id, submission_id, revealed_at
        FROM satt.top3_reveals ORDER BY viewer_user_id, submission_id
    """,
}


def configure_private_database_url() -> None:
    """Build the private container URL without exposing its components."""

    if os.environ.get("DATABASE_URL"):
        return

    names = (
        "SATT_DB_HOST",
        "SATT_DB_PORT",
        "SATT_DB_NAME",
        "SATT_DB_USER",
        "SATT_DB_PASSWORD",
    )
    values = {name: os.environ.get(name, "") for name in names}
    if any(not value for value in values.values()):
        raise RuntimeError(
            "production fingerprint is missing private database configuration"
        )

    os.environ["DATABASE_URL"] = "postgresql+asyncpg://{}:{}@{}:{}/{}".format(
        quote(values["SATT_DB_USER"], safe=""),
        quote(values["SATT_DB_PASSWORD"], safe=""),
        values["SATT_DB_HOST"],
        values["SATT_DB_PORT"],
        quote(values["SATT_DB_NAME"], safe=""),
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def fingerprint_rows(rows_by_table: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Return only row counts and a one-way digest."""

    normalized = {
        table: [_json_value(row) for row in rows]
        for table, rows in sorted(rows_by_table.items())
    }
    payload = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return {
        "counts": {table: len(rows) for table, rows in normalized.items()},
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


async def _query_group(
    queries: dict[str, str], *, optional: bool = False
) -> dict[str, list[dict[str, Any]]]:
    engine = get_engine()
    rows_by_table: dict[str, list[dict[str, Any]]] = {}
    async with engine.connect() as connection:
        for table, query in queries.items():
            if optional:
                exists = await connection.scalar(
                    text("SELECT to_regclass(:qualified_name)"),
                    {"qualified_name": f"satt.{table}"},
                )
                if exists is None:
                    rows_by_table[table] = []
                    continue
            result = await connection.execute(text(query))
            rows_by_table[table] = [dict(row) for row in result.mappings()]
    return rows_by_table


async def fingerprint_production() -> dict[str, Any]:
    settings = get_settings()
    if settings.environment != "production":
        raise RuntimeError("production fingerprint refuses a non-production runtime")
    if settings.database_environment != "production":
        raise RuntimeError("production fingerprint refuses cross-tier data")

    auth_rows = await _query_group(AUTH_QUERIES)
    data_rows = await _query_group(DATA_QUERIES)
    data_rows.update(await _query_group(OPTIONAL_DATA_QUERIES, optional=True))
    await get_engine().dispose()
    return {
        "auth": fingerprint_rows(auth_rows),
        "data": fingerprint_rows(data_rows),
    }


def main() -> int:
    configure_private_database_url()
    result = asyncio.run(fingerprint_production())
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
