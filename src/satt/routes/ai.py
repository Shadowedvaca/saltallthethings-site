"""AI proxy endpoints — all require authentication."""

from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from satt.ai_client import call_ai
from satt.auth_bridge import require_auth
from satt.crud import get_config, get_jokes
from satt.database import get_db
from satt.prompts import build_generate_jokes_prompts, build_process_idea_prompts

router = APIRouter()


# ---------------------------------------------------------------------------
# Response parsing helpers (mirror of JS _parseAIResponse / _parseJokeResponse)
# ---------------------------------------------------------------------------


def _parse_idea_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    parsed = json.loads(cleaned)
    if (
        not isinstance(parsed.get("titles"), list)
        or not parsed.get("summary")
        or not isinstance(parsed.get("outline"), list)
    ):
        raise ValueError("Response missing required fields (titles, summary, outline)")
    return {
        "titles": parsed["titles"],
        "summary": parsed["summary"],
        "outline": parsed["outline"],
    }


def _parse_joke_response(text: str) -> list[str]:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    parsed = json.loads(cleaned)
    if not isinstance(parsed, list):
        raise ValueError("Expected array of jokes")
    return [j for j in parsed if isinstance(j, str)]


# ---------------------------------------------------------------------------
# POST /api/ai/process-idea
# ---------------------------------------------------------------------------


class ProcessIdeaRequest(BaseModel):
    rawNotes: str


@router.post("/ai/process-idea")
async def process_idea(
    body: ProcessIdeaRequest,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if not body.rawNotes.strip():
        return JSONResponse(
            status_code=422, content={"error": "rawNotes must not be empty"}
        )

    config = await get_config(db)
    ai_model = config.get("aiModel", "claude")

    if ai_model == "claude" and not config.get("claudeApiKey"):
        return JSONResponse(
            status_code=400,
            content={"error": "No API key configured for claude"},
        )
    if ai_model == "openai" and not config.get("openaiApiKey"):
        return JSONResponse(
            status_code=400,
            content={"error": "No API key configured for openai"},
        )

    system_prompt, user_prompt = build_process_idea_prompts(config, body.rawNotes)

    try:
        text = await call_ai(system_prompt, user_prompt, config)
    except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
        return JSONResponse(
            status_code=500, content={"error": f"AI API error: {e}"}
        )

    try:
        result = _parse_idea_response(text)
    except (json.JSONDecodeError, ValueError) as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"AI API error: Failed to parse response: {e}"},
        )

    return JSONResponse(content=result)


# ---------------------------------------------------------------------------
# POST /api/ai/generate-jokes
# ---------------------------------------------------------------------------


class GenerateJokesRequest(BaseModel):
    themeHint: str = ""


@router.post("/ai/generate-jokes")
async def generate_jokes(
    body: GenerateJokesRequest,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    config = await get_config(db)
    ai_model = config.get("aiModel", "claude")

    if ai_model == "claude" and not config.get("claudeApiKey"):
        return JSONResponse(
            status_code=400,
            content={"error": "No API key configured for claude"},
        )
    if ai_model == "openai" and not config.get("openaiApiKey"):
        return JSONResponse(
            status_code=400,
            content={"error": "No API key configured for openai"},
        )

    all_jokes = await get_jokes(db)
    used_jokes = [j["text"] for j in all_jokes if j.get("status") == "used"]

    system_prompt, user_prompt = build_generate_jokes_prompts(
        config, used_jokes, body.themeHint
    )

    try:
        text = await call_ai(system_prompt, user_prompt, config)
    except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
        return JSONResponse(
            status_code=500, content={"error": f"AI API error: {e}"}
        )

    try:
        jokes = _parse_joke_response(text)
    except (json.JSONDecodeError, ValueError) as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"AI API error: Failed to parse response: {e}"},
        )

    return JSONResponse(content={"jokes": jokes})
