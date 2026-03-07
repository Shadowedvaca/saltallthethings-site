"""AI proxy endpoints — all require authentication."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from satt.ai_client import call_ai
from satt.auth import require_auth
from satt.crud import get_config, get_idea_and_slot, get_jokes, save_config
from satt.database import get_db
from satt.prompts import (
    build_generate_art_direction_prompts,
    build_generate_jokes_prompts,
    build_process_idea_prompts,
)

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


# ---------------------------------------------------------------------------
# Art direction defaults (seeded into satt.config on first use)
# ---------------------------------------------------------------------------

_DEFAULT_ART_STYLE_BIBLE: dict = {
    "format": "square 1024x1024",
    "artStyle": "World of Warcraft inspired fantasy digital painting, painterly, cinematic",
    "characters": {
        "bigElemental": (
            "large crystalline salt elemental, broad-shouldered and imposing, glowing cyan eyes, "
            "bronze and gold armor accents, icy blue crystal body with jagged spikes"
        ),
        "babyElementals": (
            "small chibi salt elementals, mischievous and expressive, same material language as "
            "the big elemental but tiny and comedic"
        ),
    },
    "props": ["vintage bronze microphone", "salt shaker", "glowing spilled salt"],
    "lighting": (
        "dark moody background, cool blue character highlights, warm orange torch or fire accents, "
        "high contrast cinematic rim light"
    ),
    "palette": ["icy blue", "navy", "deep purple", "bronze", "gold", "warm orange torchlight"],
    "rules": [
        "no text or words in image",
        "no real people",
        "square composition readable at thumbnail size",
        "dark moody background always present",
    ],
}

_DEFAULT_ART_ARCHETYPES: list = [
    {
        "id": "tavern_talk",
        "name": "Tavern Talk",
        "useFor": ["general discussion", "opinion episodes", "patch reactions", "community talk"],
        "scene": (
            "tavern or podcast set, microphone on table, big elemental as host behind, "
            "baby elementals acting out jokes around the table"
        ),
    },
    {
        "id": "delve_expedition",
        "name": "Delve / Cave Expedition",
        "useFor": ["exploration", "new zones", "systems discussion", "speculation", "lore-heavy"],
        "scene": (
            "cave, ruins, labyrinth, or treasure chamber, big elemental as guide or guardian, "
            "babies exploring, arguing over a map, pulling a wagon, triggering traps"
        ),
    },
    {
        "id": "raid_chaos",
        "name": "Raid / Battle Chaos",
        "useFor": ["class balance", "boss discussion", "raid prep", "major patch or expansion launch"],
        "scene": (
            "dramatic combat-ready scene, big elemental in dominant action pose, babies panicking, "
            "cheering, casting, carrying loot, spilling salt everywhere"
        ),
    },
    {
        "id": "workshop_build",
        "name": "Workshop / Build Room",
        "useFor": ["housing", "crafting", "UI or tools", "guild infrastructure", "planning episodes"],
        "scene": (
            "forge room, workshop, construction site, or blueprint table, babies building, "
            "hammering, misplacing things, big elemental supervising or facepalming"
        ),
    },
    {
        "id": "lore_vision",
        "name": "Lore Vision / Cosmic Tension",
        "useFor": ["light vs void", "story speculation", "character arcs", "philosophical discussion"],
        "scene": (
            "dramatic magical environment, split lighting blue void vs gold light, big elemental "
            "caught between forces, babies reacting to magical phenomena in funny ways"
        ),
    },
    {
        "id": "auction_house",
        "name": "Auction House / Town Comedy",
        "useFor": ["economy", "professions", "farming", "mounts", "collectibles", "side content"],
        "scene": (
            "market stall, treasure room, cluttered guild hall, mailboxes, item piles, babies "
            "selling, hoarding, sorting, fighting over loot, big elemental as merchant or banker"
        ),
    },
]


# ---------------------------------------------------------------------------
# POST /api/ai/generate-art-direction
# ---------------------------------------------------------------------------


def _parse_art_direction_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    parsed = json.loads(cleaned)
    required = [
        "topics", "tone", "archetype", "environment", "bigElementalRole",
        "babyGags", "props", "sceneSummary", "finalImagePrompt",
    ]
    for field in required:
        if field not in parsed:
            raise ValueError(f"Response missing required field: {field}")
    return {k: parsed[k] for k in required}


class GenerateArtDirectionRequest(BaseModel):
    ideaId: str
    transcriptText: str = ""


@router.post("/ai/generate-art-direction")
async def generate_art_direction(
    body: GenerateArtDirectionRequest,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if not body.transcriptText.strip():
        return JSONResponse(
            status_code=422, content={"error": "transcriptText must not be empty"}
        )

    config = await get_config(db)

    # Seed art defaults into config on first use
    changed = False
    if not config.get("artStyleBible"):
        config["artStyleBible"] = _DEFAULT_ART_STYLE_BIBLE
        changed = True
    if not config.get("artArchetypes"):
        config["artArchetypes"] = _DEFAULT_ART_ARCHETYPES
        changed = True
    if changed:
        await save_config(db, config)

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

    idea, slot = await get_idea_and_slot(db, body.ideaId)
    if idea is None:
        return JSONResponse(status_code=404, content={"error": "Idea not found"})

    episode_data = {
        "episodeNumber": slot.episode_number if slot else "",
        "title": idea.selected_title or "",
        "summary": idea.summary or "",
        "outline": idea.outline or [],
        "transcript": body.transcriptText,
    }

    system_prompt, user_prompt = build_generate_art_direction_prompts(config, episode_data)

    try:
        text = await call_ai(system_prompt, user_prompt, config)
    except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
        return JSONResponse(
            status_code=500, content={"error": f"AI API error: {e}"}
        )

    try:
        result = _parse_art_direction_response(text)
    except (json.JSONDecodeError, ValueError) as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"AI API error: Failed to parse response: {e}"},
        )

    # Update artLog — cap at 50 entries
    art_log = config.get("artLog") or []
    art_log.append({
        "episodeNum": slot.episode_num if slot else 0,
        "episodeNumber": slot.episode_number if slot else "",
        "archetypeId": result["archetype"]["id"],
        "environment": result["environment"],
        "babyGags": result["babyGags"],
        "props": result["props"],
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    })
    if len(art_log) > 50:
        art_log = art_log[-50:]
    config["artLog"] = art_log
    await save_config(db, config)

    return JSONResponse(content=result)
