import pytest

from satt.top3_contract import (
    Top3ContractError,
    validate_concept,
    validate_external_submission,
    validate_picks,
)


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


def test_external_submission_requires_named_guest_or_listener_without_owner_fields():
    assert validate_external_submission(
        {
            "id": "external-1",
            "displayName": " Guest One ",
            "externalType": "guest",
            "picks": [" First ", "Second", "Third"],
            "privateDiscussionNotes": " Shared notes ",
        }
    ) == {
        "id": "external-1",
        "displayName": "Guest One",
        "externalType": "guest",
        "picks": ["First", "Second", "Third"],
        "privateDiscussionNotes": "Shared notes",
    }

    for payload, message in (
        (
            {
                "id": "external-1",
                "displayName": "",
                "externalType": "guest",
                "picks": ["One", "Two", "Three"],
            },
            "displayName",
        ),
        (
            {
                "id": "external-1",
                "displayName": "Listener",
                "externalType": "account",
                "picks": ["One", "Two", "Three"],
            },
            "guest or listener",
        ),
        (
            {
                "id": "external-1",
                "displayName": "Listener",
                "externalType": "listener",
                "picks": ["One", "Two"],
            },
            "exactly three",
        ),
    ):
        with pytest.raises(Top3ContractError, match=message):
            validate_external_submission(payload)


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
