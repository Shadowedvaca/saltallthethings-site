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


def _compute_next_step(slot: Any) -> str:
    if not slot.production_file_key:
        return "set_key"
    inv = slot.asset_inventory or {}
    raw = inv.get("raw_audio", {})
    if not raw.get("present"):
        return "upload_raw"
    txt = inv.get("transcript_txt", {})
    if not txt.get("present"):
        return "transcribe"
    raw_modified = raw.get("modified")
    txt_modified = txt.get("modified")
    if raw_modified and txt_modified and raw_modified > txt_modified:
        return "retranscribe"
    art = inv.get("album_art", {})
    if not art.get("present"):
        return "generate_art"
    finished = inv.get("finished_audio", {})
    if not finished.get("present"):
        return "awaiting_editor"
    return "complete"


def serialize_postprod_row(slot: Any, idea: Any) -> dict:
    return {
        "slotId": slot.id,
        "episodeNumber": slot.episode_number,
        "episodeNum": slot.episode_num,
        "recordDate": _iso(slot.record_date),
        "releaseDate": _iso(slot.release_date),
        "productionFileKey": slot.production_file_key,
        "ideaId": idea.id if idea else None,
        "selectedTitle": idea.selected_title if idea else None,
        "ideaStatus": idea.status if idea else None,
        "imageFileId": idea.image_file_id if idea else None,
        "assetInventory": slot.asset_inventory,
        "transcriptionJob": slot.transcription_job,
        "nextStep": _compute_next_step(slot),
    }
