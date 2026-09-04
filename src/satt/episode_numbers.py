"""Episode-number normalization and effective-value helpers."""

from __future__ import annotations

from typing import Any


class EpisodeNumberContractError(ValueError):
    """Raised when an episode-number override is invalid or conflicts."""


def normalize_episode_number_override(value: Any) -> int | None:
    """Return a positive PostgreSQL INTEGER override or ``None``."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise EpisodeNumberContractError(
            "Episode number override must be a positive whole number"
        )
    if value < 1 or value > 2_147_483_647:
        raise EpisodeNumberContractError(
            "Episode number override must be between 1 and 2147483647"
        )
    return value


def format_episode_number(value: int) -> str:
    """Format the canonical public/display episode label."""
    return f"EP{value:03d}"


def effective_episode_number(
    automatic_label: str,
    automatic_number: int,
    override: int | None,
) -> str:
    """Return the override label when present, otherwise the legacy label."""
    if override is not None:
        return format_episode_number(override)
    return automatic_label or format_episode_number(automatic_number)


def effective_episode_value(automatic_number: int, override: int | None) -> int:
    """Return the numeric value used for assigned-show conflict checks."""
    return override if override is not None else automatic_number
