"""Private CRUD routes — all require authentication."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from satt.auth import require_auth
from satt.crud import (
    DataConflictError,
    DataNotFoundError,
    assign_idea_to_slot,
    assign_joke_to_idea,
    delete_idea,
    free_joke,
    get_assignments,
    get_config,
    get_data_revision,
    get_ideas,
    get_jokes,
    get_show_slots,
    replace_assignments,
    replace_ideas,
    replace_jokes,
    replace_show_slots,
    require_data_revision,
    save_config,
    unassign_idea_from_slot,
)
from satt.database import get_db
from satt.joke_contract import JokeContractError
from satt.outline_contract import OutlineContractError, normalize_configured_segments
from satt.song_contract import SongContractError
from satt.song_crud import get_songs, replace_songs

router = APIRouter()

_ALLOWED_KEYS = {"config", "ideas", "jokes", "songs", "showSlots", "assignments"}
_CONFIG_SECRET_KEYS = ("claudeApiKey", "openaiApiKey")


class JokeAssignmentRequest(BaseModel):
    ideaId: str


class ScheduleAssignmentRequest(BaseModel):
    ideaId: str


def _public_config(config: dict) -> dict:
    """Return browser-safe config with secret presence flags."""
    public = dict(config)
    for key in _CONFIG_SECRET_KEYS:
        public.pop(key, None)
        public[f"{key}Configured"] = bool(config.get(key))
    return public


def _merge_config_update(
    existing: dict,
    incoming: dict,
    *,
    allow_secret_updates: bool,
) -> dict:
    """Merge a config update while keeping stored API keys server-side."""
    merged = dict(existing)
    update = dict(incoming)

    for key in _CONFIG_SECRET_KEYS:
        value = update.pop(key, None)
        if value is None or value == "":
            continue
        if not isinstance(value, str):
            raise HTTPException(status_code=422, detail=f"{key} must be a string")
        value = value.strip()
        if not value:
            continue
        if not allow_secret_updates:
            raise HTTPException(
                status_code=403,
                detail="Only administrators may replace AI API keys",
            )
        merged[key] = value

    for key in tuple(update):
        if key.endswith("ApiKeyConfigured"):
            update.pop(key)

    if "segments" in update:
        try:
            update["segments"] = normalize_configured_segments(update["segments"])
        except OutlineContractError as error:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid show section configuration: {error}",
            ) from error

    merged.update(update)
    return merged


def _parse_revision(if_match: str | None) -> int:
    if if_match is None:
        raise HTTPException(
            status_code=428,
            detail="If-Match data revision is required",
        )
    value = if_match.strip()
    if value.startswith("W/"):
        value = value[2:].strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    try:
        revision = int(value)
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=422,
            detail="If-Match must contain a non-negative integer revision",
        ) from error
    if revision < 0:
        raise HTTPException(
            status_code=422,
            detail="If-Match must contain a non-negative integer revision",
        )
    return revision


async def _guard_revision(db: AsyncSession, if_match: str | None) -> None:
    expected_revision = _parse_revision(if_match)
    try:
        await require_data_revision(db, expected_revision)
    except DataConflictError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Server data changed after this page loaded. Reloaded data is required before retrying.",
                "currentRevision": error.current_revision,
            },
        ) from error


async def _export_state(db: AsyncSession) -> dict:
    config, ideas, jokes, songs, show_slots, assignments, revision = (
        await get_config(db),
        await get_ideas(db),
        await get_jokes(db),
        await get_songs(db),
        await get_show_slots(db),
        await get_assignments(db),
        await get_data_revision(db),
    )
    return {
        "config": _public_config(config),
        "ideas": ideas,
        "jokes": jokes,
        "songs": songs,
        "showSlots": show_slots,
        "assignments": assignments,
        "revision": revision,
    }


def _mutation_response(state: dict, data: Any | None = None) -> dict:
    return {
        "ok": True,
        "data": state if data is None else data,
        "state": state,
        "revision": state["revision"],
    }


@router.get("/export")
async def export_all(
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await _export_state(db)


@router.get("/data/{key}")
async def get_data(
    key: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if key not in _ALLOWED_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown key: {key!r}")
    if key == "config":
        return _public_config(await get_config(db))
    if key == "ideas":
        return await get_ideas(db)
    if key == "jokes":
        return await get_jokes(db)
    if key == "songs":
        return await get_songs(db)
    if key == "showSlots":
        return await get_show_slots(db)
    return await get_assignments(db)


@router.put("/data/{key}")
async def put_data(
    key: str,
    body: Any = Body(...),
    if_match: str | None = Header(default=None, alias="If-Match"),
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if key not in _ALLOWED_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown key: {key!r}")
    await _guard_revision(db, if_match)

    if key == "config":
        if not isinstance(body, dict):
            raise HTTPException(status_code=422, detail="config must be an object")
        existing = await get_config(db)
        merged = _merge_config_update(
            existing,
            body,
            allow_secret_updates=bool(_user.get("is_admin")),
        )
        await save_config(db, merged)
        saved = _public_config(merged)
    elif key == "ideas":
        if not isinstance(body, list):
            raise HTTPException(status_code=422, detail="ideas must be an array")
        await replace_ideas(db, body)
        saved = await get_ideas(db)
    elif key == "jokes":
        if not isinstance(body, list):
            raise HTTPException(status_code=422, detail="jokes must be an array")
        try:
            await replace_jokes(db, body)
        except JokeContractError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        saved = await get_jokes(db)
    elif key == "songs":
        if not isinstance(body, list):
            raise HTTPException(status_code=422, detail="songs must be an array")
        try:
            await replace_songs(db, body)
        except SongContractError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        saved = await get_songs(db)
    elif key == "showSlots":
        if not isinstance(body, list):
            raise HTTPException(status_code=422, detail="showSlots must be an array")
        await replace_show_slots(db, body)
        saved = await get_show_slots(db)
    else:
        if not isinstance(body, dict):
            raise HTTPException(status_code=422, detail="assignments must be an object")
        try:
            await replace_assignments(db, body)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        saved = await get_assignments(db)

    state = await _export_state(db)
    return _mutation_response(state, saved)


@router.put("/import")
async def bulk_import(
    body: dict,
    if_match: str | None = Header(default=None, alias="If-Match"),
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    unknown_keys = set(body) - _ALLOWED_KEYS
    if unknown_keys:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown import keys: {', '.join(sorted(unknown_keys))}",
        )
    expected_types = {
        "config": dict,
        "ideas": list,
        "jokes": list,
        "songs": list,
        "showSlots": list,
        "assignments": dict,
    }
    for key, expected_type in expected_types.items():
        if key in body and not isinstance(body[key], expected_type):
            type_name = "object" if expected_type is dict else "array"
            raise HTTPException(status_code=422, detail=f"{key} must be an {type_name}")

    await _guard_revision(db, if_match)
    if "config" in body:
        existing = await get_config(db)
        merged = _merge_config_update(
            existing,
            body["config"],
            allow_secret_updates=bool(_user.get("is_admin")),
        )
        await save_config(db, merged)
    if "ideas" in body:
        await replace_ideas(db, body["ideas"])
    if "jokes" in body:
        try:
            await replace_jokes(db, body["jokes"])
        except JokeContractError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    if "songs" in body:
        try:
            await replace_songs(db, body["songs"])
        except SongContractError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    if "showSlots" in body:
        await replace_show_slots(db, body["showSlots"])
    if "assignments" in body:
        try:
            await replace_assignments(db, body["assignments"])
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    state = await _export_state(db)
    return _mutation_response(state)


@router.put("/jokes/{joke_id}/assignment")
async def put_joke_assignment(
    joke_id: str,
    body: JokeAssignmentRequest,
    if_match: str | None = Header(default=None, alias="If-Match"),
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not body.ideaId.strip():
        raise HTTPException(status_code=422, detail="ideaId must not be empty")
    await _guard_revision(db, if_match)
    try:
        await assign_joke_to_idea(db, joke_id, body.ideaId.strip())
    except DataNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    state = await _export_state(db)
    return _mutation_response(state, state["jokes"])


@router.delete("/jokes/{joke_id}/assignment")
async def delete_joke_assignment(
    joke_id: str,
    if_match: str | None = Header(default=None, alias="If-Match"),
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        await free_joke(db, joke_id)
    except DataNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    state = await _export_state(db)
    return _mutation_response(state, state["jokes"])


@router.delete("/ideas/{idea_id}")
async def delete_one_idea(
    idea_id: str,
    if_match: str | None = Header(default=None, alias="If-Match"),
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        await delete_idea(db, idea_id)
    except DataNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    state = await _export_state(db)
    return _mutation_response(
        state,
        {
            "ideas": state["ideas"],
            "jokes": state["jokes"],
            "songs": state["songs"],
            "assignments": state["assignments"],
        },
    )


@router.put("/schedule/{slot_id}/assignment")
async def put_schedule_assignment(
    slot_id: str,
    body: ScheduleAssignmentRequest,
    if_match: str | None = Header(default=None, alias="If-Match"),
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not body.ideaId.strip():
        raise HTTPException(status_code=422, detail="ideaId must not be empty")
    await _guard_revision(db, if_match)
    try:
        await assign_idea_to_slot(db, body.ideaId.strip(), slot_id)
    except DataNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    state = await _export_state(db)
    return _mutation_response(
        state,
        {"ideas": state["ideas"], "assignments": state["assignments"]},
    )


@router.delete("/schedule/{slot_id}/assignment")
async def delete_schedule_assignment(
    slot_id: str,
    if_match: str | None = Header(default=None, alias="If-Match"),
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        await unassign_idea_from_slot(db, slot_id)
    except DataNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    state = await _export_state(db)
    return _mutation_response(
        state,
        {"ideas": state["ideas"], "assignments": state["assignments"]},
    )
