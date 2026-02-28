"""Serializers: Postgres ORM rows → camelCase JSON matching the JS data model."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def serialize_idea(row: Any) -> dict:
    return {
        "id": row.id,
        "titles": row.titles or [],
        "selectedTitle": row.selected_title,
        "summary": row.summary,
        "outline": row.outline or [],
        "status": row.status,
        "imageFileId": row.image_file_id,
        "rawNotes": row.raw_notes,
        "createdAt": _iso(row.created_at),
        "updatedAt": _iso(row.updated_at),
    }


def serialize_joke(row: Any) -> dict:
    return {
        "id": row.id,
        "text": row.text,
        "status": row.status,
        "source": row.source,
        "usedByIdeaId": row.used_by_idea_id,
        "createdAt": _iso(row.created_at),
    }


def serialize_show_slot(row: Any) -> dict:
    return {
        "id": row.id,
        "episodeNumber": row.episode_number,
        "episodeNum": row.episode_num,
        "recordDate": _iso(row.record_date),
        "releaseDate": _iso(row.release_date),
        "isRollout": row.is_rollout,
        "releaseDateOverride": _iso(row.release_date_override),
    }
