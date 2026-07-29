"""Canonical validation and normalization for configured show outlines."""

from __future__ import annotations

from typing import Any


class OutlineContractError(ValueError):
    """Raised when configured sections or generated outline data is invalid."""


def normalize_configured_segments(segments: Any) -> list[dict]:
    if not isinstance(segments, list) or not segments:
        raise OutlineContractError("configure at least one show section")

    normalized: list[dict] = []
    seen_ids: set[str] = set()
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise OutlineContractError(f"show section {index + 1} must be an object")

        segment_id = segment.get("id")
        name = segment.get("name")
        description = segment.get("description") or ""
        if not isinstance(segment_id, str) or not segment_id.strip():
            raise OutlineContractError(f"show section {index + 1} needs a stable id")
        if not isinstance(name, str) or not name.strip():
            raise OutlineContractError(f"show section {index + 1} needs a name")
        if not isinstance(description, str):
            raise OutlineContractError(
                f"show section {segment_id.strip()!r} description must be text"
            )

        segment_id = segment_id.strip()
        if segment_id in seen_ids:
            raise OutlineContractError(f"duplicate show section id: {segment_id!r}")
        seen_ids.add(segment_id)
        normalized.append(
            {
                "id": segment_id,
                "name": name.strip(),
                "description": description.strip(),
            }
        )

    return normalized


def normalize_generated_outline(
    outline: Any,
    configured_segments: list[dict],
) -> list[dict]:
    configured = normalize_configured_segments(configured_segments)
    if not isinstance(outline, list):
        raise OutlineContractError("outline must be an array")

    configured_by_id = {segment["id"]: segment for segment in configured}
    generated_by_id: dict[str, dict] = {}

    for index, segment in enumerate(outline):
        if not isinstance(segment, dict):
            raise OutlineContractError(f"outline section {index + 1} must be an object")

        segment_id = segment.get("segmentId")
        if not isinstance(segment_id, str) or not segment_id.strip():
            raise OutlineContractError(f"outline section {index + 1} needs segmentId")
        segment_id = segment_id.strip()
        if segment_id not in configured_by_id:
            raise OutlineContractError(f"unknown outline section id: {segment_id!r}")
        if segment_id in generated_by_id:
            raise OutlineContractError(f"duplicate outline section id: {segment_id!r}")

        talking_points = segment.get("talkingPoints")
        if not isinstance(talking_points, list):
            raise OutlineContractError(
                f"outline section {segment_id!r} talkingPoints must be an array"
            )
        cleaned_points: list[str] = []
        for point in talking_points:
            if not isinstance(point, str) or not point.strip():
                raise OutlineContractError(
                    f"outline section {segment_id!r} has an invalid talking point"
                )
            cleaned_points.append(point.strip())
        if not 2 <= len(cleaned_points) <= 5:
            raise OutlineContractError(
                f"outline section {segment_id!r} must have 2-5 talking points"
            )

        canonical = configured_by_id[segment_id]
        generated_by_id[segment_id] = {
            "segmentId": segment_id,
            "segmentName": canonical["name"],
            "talkingPoints": cleaned_points,
        }

    missing = [
        segment["id"] for segment in configured if segment["id"] not in generated_by_id
    ]
    if missing:
        raise OutlineContractError(
            "missing configured outline sections: " + ", ".join(missing)
        )

    return [generated_by_id[segment["id"]] for segment in configured]
