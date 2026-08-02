"""Validation for shared Top 3 concepts and private participant submissions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class Top3ContractError(ValueError):
    """Raised when Top 3 data cannot satisfy the privacy-safe domain contract."""


def _text(
    value: Any,
    *,
    label: str,
    maximum: int,
    required: bool = True,
) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise Top3ContractError(f"{label} must be a string")
    result = value.strip()
    if required and not result:
        raise Top3ContractError(f"{label} must not be empty")
    if len(result) > maximum:
        raise Top3ContractError(f"{label} must be at most {maximum} characters")
    return result


def _optional_text(value: Any, *, label: str, maximum: int) -> str | None:
    if value is None:
        return None
    result = _text(value, label=label, maximum=maximum, required=False)
    return result or None


def _timestamp(value: Any, *, label: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise Top3ContractError(f"{label} must be an ISO-8601 timestamp") from error
    else:
        raise Top3ContractError(f"{label} must be an ISO-8601 timestamp")
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def validate_picks(value: Any, *, label: str = "picks") -> list[str]:
    if not isinstance(value, list) or len(value) != 3:
        raise Top3ContractError(f"{label} must contain exactly three ranked picks")
    picks = [
        _text(item, label=f"{label} rank {index}", maximum=200)
        for index, item in enumerate(value, start=1)
    ]
    if len({pick.casefold() for pick in picks}) != 3:
        raise Top3ContractError(f"{label} must contain three distinct picks")
    return picks


def validate_concept(value: Any, *, concept_id: str | None = None) -> dict:
    if not isinstance(value, dict):
        raise Top3ContractError("Top 3 concept must be an object")
    canonical_id = _text(
        concept_id if concept_id is not None else value.get("id"),
        label="concept id",
        maximum=255,
    )
    example = value.get("aiExample", [])
    if example is None:
        example = []
    if example != []:
        example = validate_picks(example, label="aiExample")

    status = value.get("status", "active")
    if status not in {"active", "retired"}:
        raise Top3ContractError("status must be active or retired")
    source = value.get("source", "manual")
    if source not in {"manual", "ai"}:
        raise Top3ContractError("source must be manual or ai")

    provider = _optional_text(value.get("aiProvider"), label="aiProvider", maximum=100)
    model_id = _optional_text(value.get("aiModelId"), label="aiModelId", maximum=200)
    generated_at = _timestamp(value.get("aiGeneratedAt"), label="aiGeneratedAt")
    if source == "ai" and (not provider or not model_id or generated_at is None):
        raise Top3ContractError(
            "AI concepts require aiProvider, aiModelId, and aiGeneratedAt provenance"
        )
    if source == "manual" and any((provider, model_id, generated_at)):
        raise Top3ContractError("manual concepts cannot include AI provenance")

    return {
        "id": canonical_id,
        "name": _text(value.get("name"), label="name", maximum=200),
        "description": _text(
            value.get("description"), label="description", maximum=4000
        ),
        "rules": _text(
            value.get("rules", ""), label="rules", maximum=4000, required=False
        ),
        "hostNotes": _text(
            value.get("hostNotes", ""),
            label="hostNotes",
            maximum=8000,
            required=False,
        ),
        "aiExample": example,
        "status": status,
        "source": source,
        "aiProvider": provider,
        "aiModelId": model_id,
        "aiGeneratedAt": generated_at,
    }


def validate_account_submission(value: Any) -> dict:
    if not isinstance(value, dict):
        raise Top3ContractError("submission must be an object")
    return {
        "id": _text(value.get("id"), label="submission id", maximum=255),
        "picks": validate_picks(value.get("picks")),
        "privateDiscussionNotes": _text(
            value.get("privateDiscussionNotes", ""),
            label="privateDiscussionNotes",
            maximum=8000,
            required=False,
        ),
    }


def validate_external_submission(
    value: Any, *, submission_id: str | None = None
) -> dict:
    if not isinstance(value, dict):
        raise Top3ContractError("external submission must be an object")
    canonical_id = _text(
        submission_id if submission_id is not None else value.get("id"),
        label="submission id",
        maximum=255,
    )
    external_type = value.get("externalType")
    if external_type not in {"guest", "listener"}:
        raise Top3ContractError("externalType must be guest or listener")
    return {
        "id": canonical_id,
        "displayName": _text(
            value.get("displayName"), label="displayName", maximum=200
        ),
        "externalType": external_type,
        "picks": validate_picks(value.get("picks")),
        "privateDiscussionNotes": _text(
            value.get("privateDiscussionNotes", ""),
            label="privateDiscussionNotes",
            maximum=8000,
            required=False,
        ),
    }
