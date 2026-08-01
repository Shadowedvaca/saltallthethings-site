"""Prompt and parser contract tests for AI-assisted Top 3 proposals."""

from datetime import datetime, timezone

import pytest

from satt.prompts import build_top3_concept_prompts
from satt.top3_ai_contract import (
    Top3AIContractError,
    normalize_top3_generation_input,
    parse_generated_top3_concept,
)


INPUT = {
    "name": "Top Dungeon Snacks",
    "description": "Rank the best snacks for a long dungeon run.",
    "rules": "No conjured food.",
    "hostNotes": "Keep the examples fictional.",
}
VALID_RESPONSE = (
    '{"name":"Top Dungeon Snacks","description":"Rank three dungeon snacks.",'
    '"rules":"No conjured food; explain each rank.",'
    '"aiExample":["Cheese wheel","Spiced jerky","Moonberry juice"]}'
)


def test_prompt_preserves_supplied_name_and_treats_examples_as_fictional():
    system_prompt, user_prompt = build_top3_concept_prompts(INPUT)
    assert 'Preserve this supplied name exactly: "Top Dungeon Snacks"' in system_prompt
    assert "fictional illustrations only" in system_prompt
    assert "Do not infer or create picks" in system_prompt
    assert "Keep the examples fictional." in user_prompt


def test_missing_name_prompt_requests_a_useful_proposal():
    normalized = normalize_top3_generation_input({"description": "Rank raid moments."})
    system_prompt, _ = build_top3_concept_prompts(normalized)
    assert normalized["name"] is None
    assert "Propose a concise, useful name" in system_prompt


def test_parser_returns_save_ready_provenance_and_copied_host_notes():
    result = parse_generated_top3_concept(
        VALID_RESPONSE,
        generation_input=INPUT,
        provider="claude",
        model_id="claude-test-model",
        generated_at=datetime(2026, 8, 1, 12, 30, tzinfo=timezone.utc),
    )
    assert result["name"] == INPUT["name"]
    assert result["hostNotes"] == INPUT["hostNotes"]
    assert result["source"] == "ai"
    assert result["aiProvider"] == "claude"
    assert result["aiModelId"] == "claude-test-model"
    assert result["aiGeneratedAt"] == "2026-08-01T12:30:00Z"
    assert result["aiExample"] == [
        "Cheese wheel",
        "Spiced jerky",
        "Moonberry juice",
    ]
    assert "picks" not in result


@pytest.mark.parametrize(
    ("response", "message"),
    [
        ("not json", "valid JSON object"),
        (
            '{"name":"Changed","description":"Valid","rules":"Valid",'
            '"aiExample":["One","Two","Three"]}',
            "preserve the supplied name",
        ),
        (
            '{"name":"Top Dungeon Snacks","description":"Valid","rules":"Valid",'
            '"aiExample":["One","One","Three"]}',
            "distinct",
        ),
        (
            '{"name":"Top Dungeon Snacks","description":"Valid","rules":"Valid",'
            '"aiExample":["One","Two","Three"],"participant":"host"}',
            "contain only",
        ),
        (
            '{"name":"Top Dungeon Snacks","name":"Changed","description":"Valid",'
            '"rules":"Valid","aiExample":["One","Two","Three"]}',
            "duplicate field",
        ),
    ],
)
def test_parser_rejects_malformed_or_participant_shaped_output(response, message):
    with pytest.raises(Top3AIContractError, match=message):
        parse_generated_top3_concept(
            response,
            generation_input=INPUT,
            provider="openai",
            model_id="gpt-test",
            generated_at=datetime.now(timezone.utc),
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"description": "  "}, "description must not be empty"),
        ({"description": "x" * 4001}, "description must be at most 4000"),
        ({"description": "Valid", "hostNotes": "x" * 8001}, "hostNotes"),
    ],
)
def test_generation_input_enforces_shared_concept_lengths(payload, message):
    with pytest.raises(Top3AIContractError, match=message):
        normalize_top3_generation_input(payload)
