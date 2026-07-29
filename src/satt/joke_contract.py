"""Validation and normalization rules for the shared joke bank."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

MIN_JOKE_COUNT = 1
MAX_JOKE_COUNT = 20
MAX_JOKE_LENGTH = 500
_SPACE_RE = re.compile(r"\s+")


class JokeContractError(ValueError):
    """Raised when joke data cannot satisfy the bank contract."""


def normalize_joke_text(value: str) -> str:
    """Return a stable comparison key without changing stored display text."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = "".join(
        " " if unicodedata.category(char)[0] in {"P", "Z"} else char
        for char in normalized
    )
    return _SPACE_RE.sub(" ", normalized).strip()


def validate_joke_count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise JokeContractError("jokeCount must be an integer")
    if not MIN_JOKE_COUNT <= value <= MAX_JOKE_COUNT:
        raise JokeContractError(
            f"jokeCount must be between {MIN_JOKE_COUNT} and {MAX_JOKE_COUNT}"
        )
    return value


def _validate_text(value: Any, *, label: str) -> tuple[str, str]:
    if not isinstance(value, str):
        raise JokeContractError(f"{label} must be a string")
    text = value.strip()
    if not text:
        raise JokeContractError(f"{label} must not be empty")
    if len(text) > MAX_JOKE_LENGTH:
        raise JokeContractError(
            f"{label} must be at most {MAX_JOKE_LENGTH} characters"
        )
    comparison_key = normalize_joke_text(text)
    if not comparison_key:
        raise JokeContractError(f"{label} must contain letters or numbers")
    return text, comparison_key


def validate_generated_jokes(
    value: Any,
    *,
    expected_count: int,
    banked_jokes: list[str],
) -> list[str]:
    """Validate an AI response against its requested batch and the whole bank."""
    expected_count = validate_joke_count(expected_count)
    if not isinstance(value, list):
        raise JokeContractError("expected a JSON array of jokes")
    if len(value) != expected_count:
        raise JokeContractError(
            f"expected exactly {expected_count} jokes, received {len(value)}"
        )

    banked_keys = {
        normalize_joke_text(text)
        for text in banked_jokes
        if isinstance(text, str) and normalize_joke_text(text)
    }
    batch_keys: set[str] = set()
    validated: list[str] = []
    for index, candidate in enumerate(value, start=1):
        text, comparison_key = _validate_text(
            candidate, label=f"generated joke {index}"
        )
        if comparison_key in banked_keys:
            raise JokeContractError(
                f"generated joke {index} duplicates an existing banked joke"
            )
        if comparison_key in batch_keys:
            raise JokeContractError(
                f"generated joke {index} duplicates another generated joke"
            )
        batch_keys.add(comparison_key)
        validated.append(text)
    return validated


def validate_banked_jokes(jokes: list[dict]) -> list[dict]:
    """Return canonical bank records or reject ambiguous lifecycle data."""
    comparison_keys: set[str] = set()
    assigned_ideas: set[str] = set()
    canonical: list[dict] = []

    for index, joke in enumerate(jokes, start=1):
        if not isinstance(joke, dict):
            raise JokeContractError(f"banked joke {index} must be an object")
        if not joke.get("id"):
            raise JokeContractError(f"banked joke {index} must have an id")

        text, comparison_key = _validate_text(
            joke.get("text"), label=f"banked joke {index}"
        )
        if comparison_key in comparison_keys:
            raise JokeContractError(
                f"banked joke {index} duplicates another banked joke"
            )
        comparison_keys.add(comparison_key)

        status = joke.get("status") or "unused"
        if status == "active":
            status = "unused"
        if status not in {"unused", "used", "retired"}:
            raise JokeContractError(
                f"banked joke {index} has unsupported status {status!r}"
            )

        idea_id = joke.get("usedByIdeaId")
        if status == "used":
            if not isinstance(idea_id, str) or not idea_id.strip():
                raise JokeContractError(
                    f"banked joke {index} marked used must reference an idea"
                )
            idea_id = idea_id.strip()
            if idea_id in assigned_ideas:
                raise JokeContractError(
                    "only one used joke may be assigned to an idea"
                )
            assigned_ideas.add(idea_id)
        else:
            idea_id = None

        canonical.append(
            {
                **joke,
                "text": text,
                "status": status,
                "usedByIdeaId": idea_id,
            }
        )
    return canonical
