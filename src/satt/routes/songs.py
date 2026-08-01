"""Authenticated atomic lifecycle routes for the private Song Bank."""

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from satt.auth import require_auth
from satt.database import get_db
from satt.routes.data import _export_state, _guard_revision, _mutation_response
from satt.song_crud import (
    SongLifecycleError,
    SongNotFoundError,
    assign_song_to_idea,
    delete_song,
    free_song,
    set_song_status,
)

router = APIRouter()


class SongAssignmentRequest(BaseModel):
    ideaId: str


class SongStatusRequest(BaseModel):
    status: str


def _not_found(error: SongNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(error))


@router.put("/songs/{song_id}/assignment")
async def put_song_assignment(
    song_id: str,
    body: SongAssignmentRequest,
    if_match: str | None = Header(default=None, alias="If-Match"),
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    idea_id = body.ideaId.strip()
    if not idea_id:
        raise HTTPException(status_code=422, detail="ideaId must not be empty")
    await _guard_revision(db, if_match)
    try:
        await assign_song_to_idea(db, song_id, idea_id)
    except SongNotFoundError as error:
        raise _not_found(error) from error
    except SongLifecycleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    state = await _export_state(db)
    return _mutation_response(state, state["songs"])


@router.delete("/songs/{song_id}/assignment")
async def delete_song_assignment(
    song_id: str,
    if_match: str | None = Header(default=None, alias="If-Match"),
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        await free_song(db, song_id)
    except SongNotFoundError as error:
        raise _not_found(error) from error
    state = await _export_state(db)
    return _mutation_response(state, state["songs"])


@router.put("/songs/{song_id}/status")
async def put_song_status(
    song_id: str,
    body: SongStatusRequest,
    if_match: str | None = Header(default=None, alias="If-Match"),
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        await set_song_status(db, song_id, body.status)
    except SongNotFoundError as error:
        raise _not_found(error) from error
    except SongLifecycleError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    state = await _export_state(db)
    return _mutation_response(state, state["songs"])


@router.delete("/songs/{song_id}")
async def delete_one_song(
    song_id: str,
    if_match: str | None = Header(default=None, alias="If-Match"),
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        await delete_song(db, song_id)
    except SongNotFoundError as error:
        raise _not_found(error) from error
    state = await _export_state(db)
    return _mutation_response(state, state["songs"])
