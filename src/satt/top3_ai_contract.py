"""Strict validation for AI-generated Top 3 concept proposals."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from satt.top3_contract import Top3ContractError, validate_concept, validate_picks


class Top3AIContractError(ValueError):
    """Raised when AI generation input or output is not safe to accept."""


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
        raise Top3AIContractError(f"{label} must be a string")
    result = value.strip()
    if required and not result:
        raise Top3AIContractError(f"{label} must not be empty")
    if len(result) > maximum:
        raise Top3AIContractError(f"{label} must be at most {maximum} characters")
    return result


def normalize_top3_generation_input(value: Any) -> dict:
    """Normalize host-authored generation context without creating a submission."""
    if not isinstance(value, dict):
        raise Top3AIContractError("Top 3 generation input must be an object")
    name = _text(
        value.get("name"), label="name", maximum=200, required=False
    )
    return {
        "name": name or None,
        "description": _text(
            value.get("description"), label="description", maximum=4000
        ),
        "rules": _text(
            value.get("rules"), label="rules", maximum=4000, required=False
        ),
        "hostNotes": _text(
            value.get("hostNotes"),
            label="hostNotes",
            maximum=8000,
            required=False,
        ),
    }


def parse_generated_top3_concept(
    text: str,
    *,
    generation_input: dict,
    provider: str,
    model_id: str,
    generated_at: datetime,
) -> dict:
    """Parse one provider response into a save-ready shared concept proposal."""
    def reject_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict:
        result: dict = {}
        for key, value in pairs:
            if key in result:
                raise Top3AIContractError(f"response contains duplicate field: {key}")
            result[key] = value
        return result

    try:
        parsed = json.loads(text.strip(), object_pairs_hook=reject_duplicate_fields)
    except Top3AIContractError:
        raise
    except json.JSONDecodeError as error:
        raise Top3AIContractError("response must be one valid JSON object") from error

    if not isinstance(parsed, dict):
        raise Top3AIContractError("response must be one valid JSON object")
    expected_fields = {"name", "description", "rules", "aiExample"}
    if set(parsed) != expected_fields:
        raise Top3AIContractError(
            "response must contain only name, description, rules, and aiExample"
        )

    supplied_name = generation_input.get("name")
    generated_name = _text(parsed.get("name"), label="name", maximum=200)
    if supplied_name is not None and generated_name != supplied_name:
        raise Top3AIContractError("response must preserve the supplied name exactly")

    description = _text(
        parsed.get("description"), label="description", maximum=4000
    )
    rules = _text(parsed.get("rules"), label="rules", maximum=4000)
    try:
        examples = validate_picks(parsed.get("aiExample"), label="aiExample")
    except Top3ContractError as error:
        raise Top3AIContractError(str(error)) from error

    timestamp = generated_at
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    proposal = {
        "id": "generated-top3-preview",
        "name": generated_name,
        "description": description,
        "rules": rules,
        "hostNotes": generation_input.get("hostNotes", ""),
        "aiExample": examples,
        "status": "active",
        "source": "ai",
        "aiProvider": provider,
        "aiModelId": model_id,
        "aiGeneratedAt": timestamp,
    }
    try:
        canonical = validate_concept(proposal)
    except Top3ContractError as error:
        raise Top3AIContractError(str(error)) from error

    canonical.pop("id")
    canonical["aiGeneratedAt"] = canonical["aiGeneratedAt"].isoformat().replace(
        "+00:00", "Z"
    )
    return canonical
