"""Focused validation coverage for the reusable guest browser contract."""

import pytest

from satt.guest_contract import (
    GuestContractError,
    validate_guest_assignments,
    validate_guests,
)


def test_guest_contract_normalizes_private_fields_and_ignores_derived_values():
    [guest] = validate_guests(
        [
            {
                "id": "guest_valid-1",
                "displayName": "  Guest One  ",
                "privateNotes": "  host-only notes  ",
                "status": "archived",
                "totalAppearances": 999,
                "appearanceHistory": [{"ideaId": "forged"}],
            }
        ]
    )
    assert guest == {
        "id": "guest_valid-1",
        "displayName": "Guest One",
        "privateNotes": "host-only notes",
        "status": "archived",
        "createdAt": None,
    }


@pytest.mark.parametrize(
    "guest,detail",
    [
        ({"id": "bad id", "displayName": "Guest"}, "opaque ID"),
        ({"id": "guest", "displayName": " "}, "displayName"),
        ({"id": "guest", "displayName": "Guest", "status": "retired"}, "status"),
        ({"id": "guest", "displayName": "Guest", "privateNotes": 12}, "privateNotes"),
    ],
)
def test_guest_contract_rejects_malformed_records(guest: dict, detail: str):
    with pytest.raises(GuestContractError, match=detail):
        validate_guests([guest])


def test_guest_contract_rejects_duplicate_ids_and_assignment_pairs():
    with pytest.raises(GuestContractError, match="duplicates another guest id"):
        validate_guests(
            [
                {"id": "same", "displayName": "One"},
                {"id": "same", "displayName": "Two"},
            ]
        )
    with pytest.raises(GuestContractError, match="duplicates another guest/idea pair"):
        validate_guest_assignments(
            [
                {"guestId": "guest", "ideaId": "idea"},
                {"guestId": "guest", "ideaId": "idea"},
            ]
        )
