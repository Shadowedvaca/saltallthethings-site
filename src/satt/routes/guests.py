"""Authenticated lifecycle routes for reusable private guests."""

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from satt.auth import require_auth
from satt.database import get_db
from satt.guest_contract import GuestContractError
from satt.guest_crud import (
    GuestLifecycleError,
    GuestNotFoundError,
    assign_guest_to_idea,
    delete_guest,
    set_guest_status,
    unassign_guest_from_idea,
)
from satt.routes.data import _export_state, _guard_revision, _mutation_response


router = APIRouter()


class GuestStatusRequest(BaseModel):
    status: str


def _translate(error: Exception) -> HTTPException:
    if isinstance(error, GuestNotFoundError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, GuestLifecycleError):
        return HTTPException(status_code=409, detail=str(error))
    return HTTPException(status_code=422, detail=str(error))


@router.put("/guests/{guest_id}/assignments/{idea_id}")
async def put_guest_assignment(
    guest_id: str,
    idea_id: str,
    if_match: str | None = Header(default=None, alias="If-Match"),
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        await assign_guest_to_idea(db, guest_id, idea_id)
    except (GuestNotFoundError, GuestLifecycleError, GuestContractError) as error:
        raise _translate(error) from error
    state = await _export_state(db)
    return _mutation_response(
        state,
        {"guests": state["guests"], "guestAssignments": state["guestAssignments"]},
    )


@router.delete("/guests/{guest_id}/assignments/{idea_id}")
async def delete_guest_assignment(
    guest_id: str,
    idea_id: str,
    if_match: str | None = Header(default=None, alias="If-Match"),
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        await unassign_guest_from_idea(db, guest_id, idea_id)
    except GuestContractError as error:
        raise _translate(error) from error
    state = await _export_state(db)
    return _mutation_response(
        state,
        {"guests": state["guests"], "guestAssignments": state["guestAssignments"]},
    )


@router.put("/guests/{guest_id}/status")
async def put_guest_status(
    guest_id: str,
    body: GuestStatusRequest,
    if_match: str | None = Header(default=None, alias="If-Match"),
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        await set_guest_status(db, guest_id, body.status)
    except (GuestNotFoundError, GuestContractError) as error:
        raise _translate(error) from error
    state = await _export_state(db)
    return _mutation_response(state, state["guests"])


@router.delete("/guests/{guest_id}")
async def delete_one_guest(
    guest_id: str,
    if_match: str | None = Header(default=None, alias="If-Match"),
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        await delete_guest(db, guest_id)
    except (GuestNotFoundError, GuestLifecycleError, GuestContractError) as error:
        raise _translate(error) from error
    state = await _export_state(db)
    return _mutation_response(state, state["guests"])
