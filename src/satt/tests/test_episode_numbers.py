"""Unit coverage for canonical episode-number precedence and validation."""

import pytest

from satt.crud import validate_assigned_episode_numbers
from satt.episode_numbers import (
    EpisodeNumberContractError,
    effective_episode_number,
    effective_episode_value,
    format_episode_number,
    normalize_episode_number_override,
)


def test_episode_number_override_normalization_is_strict():
    assert normalize_episode_number_override(None) is None
    assert normalize_episode_number_override(42) == 42
    for invalid in (True, False, "42", 0, -1, 2_147_483_648, 1.5):
        with pytest.raises(EpisodeNumberContractError):
            normalize_episode_number_override(invalid)


def test_effective_episode_number_prefers_override_and_restores_automatic():
    assert format_episode_number(7) == "EP007"
    assert effective_episode_number("EP041", 41, 40) == "EP040"
    assert effective_episode_value(41, 40) == 40
    assert effective_episode_number("EP041", 41, None) == "EP041"
    assert effective_episode_value(41, None) == 41
    assert effective_episode_number("", 41, None) == "EP041"


class _AssignedNumberResult:
    def __init__(self, rows):
        self.rows = rows

    def __iter__(self):
        return iter(self.rows)


class _AssignedNumberDatabase:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _statement):
        return _AssignedNumberResult(self.rows)


@pytest.mark.asyncio
async def test_assigned_number_validator_accepts_unique_and_rejects_duplicates():
    await validate_assigned_episode_numbers(
        _AssignedNumberDatabase([
            ("slot-1", 1, None),
            ("slot-2", 2, 3),
        ])
    )
    with pytest.raises(EpisodeNumberContractError, match="EP003"):
        await validate_assigned_episode_numbers(
            _AssignedNumberDatabase([
                ("slot-2", 2, 3),
                ("slot-3", 3, None),
            ])
        )
