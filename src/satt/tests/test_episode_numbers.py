"""Unit coverage for canonical episode-number precedence and validation."""

import pytest

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
