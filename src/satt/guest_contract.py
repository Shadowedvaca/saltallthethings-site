"""Validation and normalization for reusable private guest records."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any


_OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,254}$")


class GuestContractError(ValueError):
    """Raised when Guest Bank data violates the browser contract."""


def validate_opaque_id(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _OPAQUE_ID.fullmatch(value):
        raise GuestContractError(
            f"{label} must be a 1-255 character opaque ID using letters, numbers, '_' or '-'"
        )
    return value


def _text(value: Any, *, label: str, maximum: int, required: bool = True) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise GuestContractError(f"{label} must be a string")
    result = value.strip()
    if required and not result:
        raise GuestContractError(f"{label} must not be empty")
    if len(result) > maximum:
        raise GuestContractError(f"{label} must be at most {maximum} characters")
    return result


def parse_timestamp(value: Any, *, label: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise GuestContractError(
                f"{label} must be an ISO-8601 timestamp"
            ) from error
    else:
        raise GuestContractError(f"{label} must be an ISO-8601 timestamp")
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def validate_guests(value: Any) -> list[dict]:
    if not isinstance(value, list):
        raise GuestContractError("guests must be an array")
    seen: set[str] = set()
    canonical: list[dict] = []
    for index, guest in enumerate(value, start=1):
        if not isinstance(guest, dict):
            raise GuestContractError(f"guest {index} must be an object")
        guest_id = validate_opaque_id(guest.get("id"), label=f"guest {index} id")
        if guest_id in seen:
            raise GuestContractError(f"guest {index} duplicates another guest id")
        seen.add(guest_id)
        status = guest.get("status", "active")
        if status not in {"active", "archived"}:
            raise GuestContractError(f"guest {index} status must be active or archived")
        canonical.append(
            {
                "id": guest_id,
                "displayName": _text(
                    guest.get("displayName"),
                    label=f"guest {index} displayName",
                    maximum=200,
                ),
                "privateNotes": _text(
                    guest.get("privateNotes", ""),
                    label=f"guest {index} privateNotes",
                    maximum=8000,
                    required=False,
                ),
                "status": status,
                "createdAt": parse_timestamp(
                    guest.get("createdAt"), label=f"guest {index} createdAt"
                ),
            }
        )
    return canonical


def validate_guest_assignments(value: Any) -> list[dict]:
    if not isinstance(value, list):
        raise GuestContractError("guestAssignments must be an array")
    seen: set[tuple[str, str]] = set()
    canonical: list[dict] = []
    for index, assignment in enumerate(value, start=1):
        if not isinstance(assignment, dict):
            raise GuestContractError(f"guest assignment {index} must be an object")
        guest_id = validate_opaque_id(
            assignment.get("guestId"), label=f"guest assignment {index} guestId"
        )
        idea_id = validate_opaque_id(
            assignment.get("ideaId"), label=f"guest assignment {index} ideaId"
        )
        pair = (guest_id, idea_id)
        if pair in seen:
            raise GuestContractError(
                f"guest assignment {index} duplicates another guest/idea pair"
            )
        seen.add(pair)
        canonical.append(
            {
                "guestId": guest_id,
                "ideaId": idea_id,
                "assignedAt": parse_timestamp(
                    assignment.get("assignedAt"),
                    label=f"guest assignment {index} assignedAt",
                ),
            }
        )
    return canonical
