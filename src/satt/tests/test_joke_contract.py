"""Unit coverage for the joke bank's normalization and lifecycle contract."""

import pytest

from satt.joke_contract import (
    JokeContractError,
    normalize_joke_text,
    validate_banked_jokes,
    validate_generated_jokes,
)


def test_normalized_comparison_ignores_case_spacing_and_punctuation():
    assert normalize_joke_text("  SAME—Joke!! ") == normalize_joke_text("same joke")


def test_generated_batch_preserves_trimmed_display_text():
    assert validate_generated_jokes(
        ["  First joke  ", "Second joke"],
        expected_count=2,
        banked_jokes=[],
    ) == ["First joke", "Second joke"]


def test_banked_jokes_reject_normalized_duplicates():
    with pytest.raises(JokeContractError, match="duplicates another banked joke"):
        validate_banked_jokes(
            [
                {"id": "one", "text": "Salt joke!", "status": "unused"},
                {"id": "two", "text": "SALT—JOKE", "status": "unused"},
            ]
        )


def test_banked_jokes_allow_only_one_used_joke_per_idea():
    with pytest.raises(JokeContractError, match="only one used joke"):
        validate_banked_jokes(
            [
                {
                    "id": "one",
                    "text": "First",
                    "status": "used",
                    "usedByIdeaId": "idea",
                },
                {
                    "id": "two",
                    "text": "Second",
                    "status": "used",
                    "usedByIdeaId": "idea",
                },
            ]
        )


def test_retired_joke_is_canonicalized_as_unassigned():
    [joke] = validate_banked_jokes(
        [
            {
                "id": "one",
                "text": "First",
                "status": "retired",
                "usedByIdeaId": "stale-idea",
            }
        ]
    )
    assert joke["usedByIdeaId"] is None
