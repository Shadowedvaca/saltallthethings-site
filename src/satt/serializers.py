"""Serializers: Postgres ORM rows → camelCase JSON matching the JS data model."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from satt.episode_numbers import effective_episode_number


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
        "aiProvider": row.ai_provider,
        "aiModelId": row.ai_model_id,
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


def serialize_song(row: Any) -> dict:
    return {
        "id": row.id,
        "artist": row.artist,
        "title": row.title,
        "youtubeUrl": row.youtube_url,
        "privateNotes": row.private_notes,
        "status": row.status,
        "assignedIdeaId": row.assigned_idea_id,
        "createdAt": _iso(row.created_at),
        "updatedAt": _iso(row.updated_at),
    }


def serialize_guest(
    row: Any,
    *,
    total_appearances: int = 0,
    first_appearance: date | None = None,
    most_recent_appearance: date | None = None,
    appearance_history: list[dict] | None = None,
) -> dict:
    return {
        "id": row.id,
        "displayName": row.display_name,
        "privateNotes": row.private_notes,
        "status": row.status,
        "createdAt": _iso(row.created_at),
        "updatedAt": _iso(row.updated_at),
        "totalAppearances": total_appearances,
        "firstAppearance": _iso(first_appearance),
        "mostRecentAppearance": _iso(most_recent_appearance),
        "appearanceHistory": appearance_history or [],
    }


def serialize_guest_assignment(row: Any) -> dict:
    return {
        "guestId": row.guest_id,
        "ideaId": row.idea_id,
        "assignedAt": _iso(row.assigned_at),
    }


def serialize_top3_concept(row: Any) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "rules": row.rules,
        "hostNotes": row.host_notes,
        "aiExample": list(row.ai_example or []),
        "status": row.status,
        "source": row.source,
        "aiProvider": row.ai_provider,
        "aiModelId": row.ai_model_id,
        "aiGeneratedAt": _iso(row.ai_generated_at),
        "createdByUserId": row.created_by_user_id,
        "createdAt": _iso(row.created_at),
        "updatedAt": _iso(row.updated_at),
    }


def serialize_top3_submission(
    row: Any,
    *,
    display_name: str,
    current_user_id: int,
    revealed_at: Any = None,
) -> dict:
    is_current_user = (
        row.participant_type == "account" and row.account_user_id == current_user_id
    )
    revealed = revealed_at is not None
    can_read_private = row.participant_type == "external" or is_current_user or revealed
    result = {
        "submissionId": row.id,
        "contributorType": row.participant_type,
        "externalType": row.external_type,
        "displayName": display_name,
        "complete": True,
        "isCurrentUser": is_current_user,
        "revealed": bool(revealed),
    }
    if can_read_private:
        result["picks"] = [row.pick_1, row.pick_2, row.pick_3]
        result["privateDiscussionNotes"] = row.private_discussion_notes
        result["createdAt"] = _iso(row.created_at)
        result["updatedAt"] = _iso(row.updated_at)
    if revealed:
        result["revealedAt"] = _iso(revealed_at)
    if row.participant_type == "external":
        result["enteredByUserId"] = row.entered_by_user_id
    return result


def serialize_show_slot(row: Any) -> dict:
    return {
        "id": row.id,
        "episodeNumber": row.episode_number,
        "episodeNum": row.episode_num,
        "episodeNumberOverride": row.episode_number_override,
        "effectiveEpisodeNumber": effective_episode_number(
            row.episode_number,
            row.episode_num,
            row.episode_number_override,
        ),
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
        "episodeNumber": effective_episode_number(
            slot.episode_number,
            slot.episode_num,
            slot.episode_number_override,
        ),
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
