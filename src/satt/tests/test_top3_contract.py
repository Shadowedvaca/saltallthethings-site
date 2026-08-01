import pytest

from satt.top3_contract import Top3ContractError, validate_concept, validate_picks


def test_picks_require_exactly_three_distinct_ranked_values():
    assert validate_picks([" First ", "Second", "Third"]) == [
        "First",
        "Second",
        "Third",
    ]
    with pytest.raises(Top3ContractError, match="exactly three"):
        validate_picks(["One", "Two"])
    with pytest.raises(Top3ContractError, match="distinct"):
        validate_picks(["One", "one", "Three"])


def test_ai_concept_requires_complete_provenance():
    with pytest.raises(Top3ContractError, match="require"):
        validate_concept(
            {
                "id": "concept",
                "name": "List",
                "description": "Description",
                "source": "ai",
                "aiExample": ["One", "Two", "Three"],
            }
        )


def test_manual_concept_rejects_misleading_ai_provenance():
    with pytest.raises(Top3ContractError, match="manual concepts"):
        validate_concept(
            {
                "id": "concept",
                "name": "List",
                "description": "Description",
                "aiProvider": "provider",
            }
        )
