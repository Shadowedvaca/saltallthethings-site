"""Direct branch coverage for the episode-number route and CRUD contracts."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from satt.crud import (
    DataNotFoundError,
    replace_show_slots,
    set_episode_number_override,
)
from satt.episode_numbers import EpisodeNumberContractError
from satt.routes.data import (
    EpisodeNumberOverrideRequest,
    ScheduleAssignmentRequest,
    delete_episode_number_override,
    put_episode_number_override,
    put_schedule_assignment,
)


class _CrudDatabase:
    def __init__(self, slot):
        self.slot = slot

    async def execute(self, _statement):
        return []

    async def scalar(self, _statement):
        return self.slot

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_show_slot_replacement_runs_effective_number_validation():
    slot = {
        "id": "slot-7",
        "episodeNumber": "EP007",
        "episodeNum": 7,
        "episodeNumberOverride": 6,
        "recordDate": "2026-09-01",
        "releaseDate": "2026-09-08",
        "isRollout": False,
        "releaseDateOverride": None,
    }
    database = _CrudDatabase(None)
    with patch("satt.crud._lock_schedule_lifecycle", new=AsyncMock()):
        with patch("satt.crud.validate_assigned_episode_numbers", new=AsyncMock()) as validate:
            with patch("satt.crud.bump_data_revision", new=AsyncMock()):
                await replace_show_slots(database, [slot])
    validate.assert_awaited_once_with(database)


@pytest.mark.asyncio
async def test_episode_number_crud_rejects_missing_and_updates_existing_slot():
    with pytest.raises(DataNotFoundError, match="Show slot not found"):
        await set_episode_number_override(_CrudDatabase(None), "missing", 7)

    slot = type("Slot", (), {"episode_number_override": None})()
    with patch("satt.crud.validate_assigned_episode_numbers", new=AsyncMock()):
        with patch("satt.crud.bump_data_revision", new=AsyncMock()):
            await set_episode_number_override(_CrudDatabase(slot), "slot-7", 7)
    assert slot.episode_number_override == 7


@pytest.mark.asyncio
async def test_episode_number_routes_map_success_and_contract_errors():
    state = {"showSlots": [{"id": "slot-7"}], "ideas": [], "assignments": {}, "revision": 5}
    guard = AsyncMock()
    save = AsyncMock()
    export = AsyncMock(return_value=state)
    with patch("satt.routes.data._guard_revision", new=guard):
        with patch("satt.routes.data.set_episode_number_override", new=save):
            with patch("satt.routes.data._export_state", new=export):
                put_result = await put_episode_number_override(
                    "slot-7",
                    EpisodeNumberOverrideRequest(episodeNumber=7),
                    if_match="3",
                    _user={},
                    db=object(),
                )
                delete_result = await delete_episode_number_override(
                    "slot-7", if_match="4", _user={}, db=object()
                )
    assert put_result["data"] == state["showSlots"]
    assert delete_result["data"] == state["showSlots"]
    assert save.await_args_list[0].args[2] == 7
    assert save.await_args_list[1].args[2] is None

    for error, expected_status in (
        (DataNotFoundError("missing"), 404),
        (EpisodeNumberContractError("conflict"), 422),
    ):
        with patch("satt.routes.data._guard_revision", new=AsyncMock()):
            with patch(
                "satt.routes.data.set_episode_number_override",
                new=AsyncMock(side_effect=error),
            ):
                with pytest.raises(HTTPException) as caught:
                    await put_episode_number_override(
                        "slot-7",
                        EpisodeNumberOverrideRequest(episodeNumber=7),
                        if_match=None,
                        _user={},
                        db=object(),
                    )
        assert caught.value.status_code == expected_status

    with patch("satt.routes.data._guard_revision", new=AsyncMock()):
        with patch(
            "satt.routes.data.set_episode_number_override",
            new=AsyncMock(side_effect=DataNotFoundError("missing")),
        ):
            with pytest.raises(HTTPException) as caught:
                await delete_episode_number_override(
                    "slot-7", if_match=None, _user={}, db=object()
                )
    assert caught.value.status_code == 404


@pytest.mark.asyncio
async def test_assignment_route_maps_episode_number_conflicts():
    with patch("satt.routes.data._guard_revision", new=AsyncMock()):
        with patch(
            "satt.routes.data.assign_idea_to_slot",
            new=AsyncMock(side_effect=EpisodeNumberContractError("EP007 conflict")),
        ):
            with pytest.raises(HTTPException) as caught:
                await put_schedule_assignment(
                    "slot-7",
                    ScheduleAssignmentRequest(ideaId="idea-7"),
                    if_match=None,
                    _user={},
                    db=object(),
                )
    assert caught.value.status_code == 422
