"""Authenticated Top 3 routes with server-enforced viewer redaction."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from satt.auth import require_auth
from satt.crud import get_data_revision
from satt.database import get_db
from satt.routes.data import _guard_revision
from satt.top3_contract import (
    Top3ContractError,
    validate_account_submission,
    validate_concept,
    validate_external_submission,
)
from satt.top3_crud import (
    Top3ConflictError,
    Top3NotFoundError,
    assign_concept,
    create_concept,
    create_external_submission,
    delete_concept,
    delete_current_submission,
    delete_external_submission,
    get_viewer_assignment,
    get_spotify_results,
    list_concepts,
    remove_assignment,
    reveal_submission,
    save_current_submission,
    update_concept,
    update_external_submission,
)

router = APIRouter()


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConceptBody(StrictBody):
    id: str | None = None
    name: str
    description: str
    rules: str = ""
    hostNotes: str = ""
    aiExample: list[str] = Field(default_factory=list)
    status: str = "active"
    source: str = "manual"
    aiProvider: str | None = None
    aiModelId: str | None = None
    aiGeneratedAt: datetime | None = None


class AssignmentBody(StrictBody):
    conceptId: str


class SubmissionBody(StrictBody):
    id: str
    picks: list[str]
    privateDiscussionNotes: str = ""


class ExternalSubmissionBody(StrictBody):
    id: str | None = None
    displayName: str
    externalType: str
    picks: list[str]
    privateDiscussionNotes: str = ""


class SpotifyResultsBody(StrictBody):
    purpose: Literal["spotify-overview"]


def _user_id(user: dict) -> int:
    value = user.get("user_id")
    if not isinstance(value, int):
        raise HTTPException(status_code=401, detail="Invalid authenticated user")
    return value


def _translate(error: Exception) -> HTTPException:
    if isinstance(error, Top3NotFoundError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, Top3ConflictError):
        return HTTPException(status_code=409, detail=str(error))
    return HTTPException(status_code=422, detail=str(error))


@router.get("/top3/concepts")
async def get_concepts(
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return {
        "revision": await get_data_revision(db),
        "concepts": await list_concepts(db),
    }


@router.post("/top3/concepts", status_code=201)
async def post_concept(
    body: ConceptBody,
    if_match: str | None = Header(default=None, alias="If-Match"),
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        concept = validate_concept(body.model_dump())
        saved = await create_concept(db, concept, _user_id(user))
    except (Top3ContractError, Top3ConflictError) as error:
        raise _translate(error) from error
    return {"revision": await get_data_revision(db), "concept": saved}


@router.put("/top3/concepts/{concept_id}")
async def put_concept(
    concept_id: str,
    body: ConceptBody,
    if_match: str | None = Header(default=None, alias="If-Match"),
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        concept = validate_concept(body.model_dump(), concept_id=concept_id)
        saved = await update_concept(db, concept)
    except (Top3ContractError, Top3NotFoundError) as error:
        raise _translate(error) from error
    return {"revision": await get_data_revision(db), "concept": saved}


@router.delete("/top3/concepts/{concept_id}")
async def remove_concept(
    concept_id: str,
    if_match: str | None = Header(default=None, alias="If-Match"),
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        await delete_concept(db, concept_id)
    except (Top3NotFoundError, Top3ConflictError) as error:
        raise _translate(error) from error
    return {"revision": await get_data_revision(db), "deleted": True}


@router.get("/top3/episodes/{idea_id}")
async def get_episode_top3(
    idea_id: str,
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await get_viewer_assignment(
        db, idea_id=idea_id, viewer_user_id=_user_id(user)
    )


@router.post("/top3/episodes/{idea_id}/spotify-results")
async def post_spotify_results(
    idea_id: str,
    _body: SpotifyResultsBody,
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return {
        "top3": await get_spotify_results(
            db, idea_id=idea_id, viewer_user_id=_user_id(user)
        )
    }


@router.put("/top3/episodes/{idea_id}/assignment")
async def put_episode_assignment(
    idea_id: str,
    body: AssignmentBody,
    if_match: str | None = Header(default=None, alias="If-Match"),
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    concept_id = body.conceptId.strip()
    if not concept_id:
        raise HTTPException(status_code=422, detail="conceptId must not be empty")
    try:
        await assign_concept(
            db,
            idea_id=idea_id,
            concept_id=concept_id,
            user_id=_user_id(user),
        )
    except (Top3NotFoundError, Top3ConflictError) as error:
        raise _translate(error) from error
    return await get_viewer_assignment(
        db, idea_id=idea_id, viewer_user_id=_user_id(user)
    )


@router.delete("/top3/episodes/{idea_id}/assignment")
async def delete_episode_assignment(
    idea_id: str,
    if_match: str | None = Header(default=None, alias="If-Match"),
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        await remove_assignment(db, idea_id)
    except Top3NotFoundError as error:
        raise _translate(error) from error
    return await get_viewer_assignment(
        db, idea_id=idea_id, viewer_user_id=_user_id(user)
    )


@router.put("/top3/episodes/{idea_id}/submission")
async def put_current_submission(
    idea_id: str,
    body: SubmissionBody,
    if_match: str | None = Header(default=None, alias="If-Match"),
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        submission = validate_account_submission(body.model_dump())
        await save_current_submission(
            db,
            idea_id=idea_id,
            user_id=_user_id(user),
            submission=submission,
        )
    except (Top3ContractError, Top3NotFoundError, Top3ConflictError) as error:
        raise _translate(error) from error
    return await get_viewer_assignment(
        db, idea_id=idea_id, viewer_user_id=_user_id(user)
    )


@router.delete("/top3/episodes/{idea_id}/submission")
async def remove_current_submission(
    idea_id: str,
    if_match: str | None = Header(default=None, alias="If-Match"),
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        await delete_current_submission(
            db, idea_id=idea_id, user_id=_user_id(user)
        )
    except Top3NotFoundError as error:
        raise _translate(error) from error
    return await get_viewer_assignment(
        db, idea_id=idea_id, viewer_user_id=_user_id(user)
    )


@router.post("/top3/episodes/{idea_id}/reveals/{submission_id}")
async def post_viewer_reveal(
    idea_id: str,
    submission_id: str,
    if_match: str | None = Header(default=None, alias="If-Match"),
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        await reveal_submission(
            db,
            idea_id=idea_id,
            submission_id=submission_id,
            viewer_user_id=_user_id(user),
        )
    except (Top3NotFoundError, Top3ConflictError) as error:
        raise _translate(error) from error
    return await get_viewer_assignment(
        db, idea_id=idea_id, viewer_user_id=_user_id(user)
    )


@router.post(
    "/top3/episodes/{idea_id}/external-submissions", status_code=201
)
async def post_external_submission(
    idea_id: str,
    body: ExternalSubmissionBody,
    if_match: str | None = Header(default=None, alias="If-Match"),
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        submission = validate_external_submission(body.model_dump())
        await create_external_submission(
            db,
            idea_id=idea_id,
            user_id=_user_id(user),
            submission=submission,
        )
    except (Top3ContractError, Top3NotFoundError, Top3ConflictError) as error:
        raise _translate(error) from error
    return await get_viewer_assignment(
        db, idea_id=idea_id, viewer_user_id=_user_id(user)
    )


@router.put(
    "/top3/episodes/{idea_id}/external-submissions/{submission_id}"
)
async def put_external_submission(
    idea_id: str,
    submission_id: str,
    body: ExternalSubmissionBody,
    if_match: str | None = Header(default=None, alias="If-Match"),
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        submission = validate_external_submission(
            body.model_dump(), submission_id=submission_id
        )
        await update_external_submission(db, idea_id=idea_id, submission=submission)
    except (Top3ContractError, Top3NotFoundError, Top3ConflictError) as error:
        raise _translate(error) from error
    return await get_viewer_assignment(
        db, idea_id=idea_id, viewer_user_id=_user_id(user)
    )


@router.delete(
    "/top3/episodes/{idea_id}/external-submissions/{submission_id}"
)
async def remove_external_submission(
    idea_id: str,
    submission_id: str,
    if_match: str | None = Header(default=None, alias="If-Match"),
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _guard_revision(db, if_match)
    try:
        await delete_external_submission(
            db, idea_id=idea_id, submission_id=submission_id
        )
    except Top3NotFoundError as error:
        raise _translate(error) from error
    return await get_viewer_assignment(
        db, idea_id=idea_id, viewer_user_id=_user_id(user)
    )
