"""Focused tests for configured show-section and generated outline integrity."""

from __future__ import annotations

import pytest

from satt.outline_contract import (
    OutlineContractError,
    normalize_configured_segments,
    normalize_generated_outline,
)


SEGMENTS = [
    {"id": "opening", "name": "Opening", "description": "Start here"},
    {"id": "main", "name": "Main Topic", "description": "Core discussion"},
]


def _section(segment_id: str, name: str = "ignored") -> dict:
    return {
        "segmentId": segment_id,
        "segmentName": name,
        "talkingPoints": ["First point", "Second point"],
    }


def test_reordered_outline_is_normalized_to_configured_order_and_names():
    normalized = normalize_generated_outline(
        [_section("main"), _section("opening")],
        SEGMENTS,
    )
    assert [section["segmentId"] for section in normalized] == ["opening", "main"]
    assert [section["segmentName"] for section in normalized] == [
        "Opening",
        "Main Topic",
    ]


@pytest.mark.parametrize(
    ("outline", "message"),
    [
        ([_section("opening")], "missing configured"),
        (
            [_section("opening"), _section("opening"), _section("main")],
            "duplicate outline",
        ),
        ([_section("opening"), _section("unknown")], "unknown outline"),
        (
            [
                _section("opening"),
                {"segmentId": "main", "talkingPoints": "not-an-array"},
            ],
            "talkingPoints must be an array",
        ),
        (
            [
                _section("opening"),
                {"segmentId": "main", "talkingPoints": ["only one"]},
            ],
            "must have 2-5 talking points",
        ),
    ],
)
def test_malformed_generated_outline_is_rejected(outline, message):
    with pytest.raises(OutlineContractError, match=message):
        normalize_generated_outline(outline, SEGMENTS)


def test_empty_configuration_is_explicitly_rejected():
    with pytest.raises(OutlineContractError, match="at least one"):
        normalize_configured_segments([])


def test_custom_configuration_requires_stable_unique_ids():
    with pytest.raises(OutlineContractError, match="duplicate"):
        normalize_configured_segments(
            [
                {"id": "custom", "name": "One"},
                {"id": "custom", "name": "Two"},
            ]
        )
