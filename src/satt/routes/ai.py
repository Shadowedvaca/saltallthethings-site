"""AI proxy endpoints — all require authentication."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from satt.ai_client import call_ai, call_dalle
from satt.auth import require_auth
from satt.config import get_settings
from satt.crud import get_config, get_idea_and_slot, get_jokes, save_config, set_asset_inventory, set_idea_image_file_id
from satt.database import get_db
from satt.gdrive import (
    build_asset_inventory,
    delete_file,
    fetch_file_content,
    fetch_image_as_base64,
    get_drive_access_token,
    list_folder_files,
    upload_file_to_folder,
)
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

_ART_STYLE_BIBLE_VERSION = 2

_DEFAULT_ART_STYLE_BIBLE: dict = {
    "version": _ART_STYLE_BIBLE_VERSION,
    "format": "square 1024x1024",
    "artStyle": (
        "World of Warcraft inspired fantasy digital painting, painterly, cinematic. "
        "Think Blizzard cinematic concept art crossed with illustrated podcast branding — "
        "rich saturated colors, high detail, dramatic lighting."
    ),
    "characters": {
        "bigElemental": (
            "LARGE crystalline salt elemental — the main mascot. Imposing and broad-shouldered. "
            "Body made of jagged icy-blue salt crystals with glowing cyan eyes. "
            "Wears bronze and gold armor bands and pauldrons. Radiates authority and gravitas."
        ),
        "babyElementals": (
            "SMALL chibi salt elementals — mischievous sidekicks. Same crystal material as the "
            "big elemental but tiny, chibi-proportioned, with oversized expressive faces. "
            "Always doing something funny or chaotic related to the episode topic."
        ),
    },
    "props": [
        "vintage bronze podcast microphone",
        "glass salt shakers with metal lids",
        "tipped-over salt shakers pouring glowing magical salt",
        "glowing spilled salt (treat as magical particles)",
    ],
    "lighting": (
        "dark moody background, cool blue character highlights from crystal glow, "
        "warm orange torch or fire accents for contrast, high contrast cinematic rim light"
    ),
    "palette": [
        "icy blue and white (elementals)",
        "deep navy and purple/black (backgrounds)",
        "bronze and gold (armor accents)",
        "warm orange torchlight (accent lighting)",
    ],
    "rules": [
        "NO text, words, letters, or numbers anywhere in the image",
        "no real people or recognizable WoW characters by name",
        "square composition readable at thumbnail size",
        "dark moody background always present",
        "always feature salt elementals as the characters",
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


@router.post("/ai/generate-art-direction")
async def generate_art_direction(
    body: GenerateArtDirectionRequest,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    config = await get_config(db)

    # Seed art defaults (or upgrade if version is outdated)
    changed = False
    existing_version = (config.get("artStyleBible") or {}).get("version", 0)
    if not config.get("artStyleBible") or existing_version < _ART_STYLE_BIBLE_VERSION:
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

    # Fetch transcript from Google Drive via backend OAuth credentials
    settings = get_settings()
    inv = (slot.asset_inventory or {}) if slot else {}
    transcript_asset = inv.get("transcript_txt", {})
    drive_file_id = transcript_asset.get("drive_file_id")

    if not drive_file_id:
        return JSONResponse(
            status_code=400,
            content={"error": "No transcript file found in asset inventory. Scan assets first."},
        )
    if not all([
        settings.google_oauth_client_id,
        settings.google_oauth_client_secret,
        settings.google_oauth_refresh_token,
    ]):
        return JSONResponse(
            status_code=400,
            content={"error": "Google Drive OAuth not configured on server."},
        )

    try:
        access_token = await get_drive_access_token(
            settings.google_oauth_client_id,
            settings.google_oauth_client_secret,
            settings.google_oauth_refresh_token,
        )
        transcript_text = await fetch_file_content(access_token, drive_file_id)
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to fetch transcript from Drive: {e}"},
        )

    episode_data = {
        "episodeNumber": slot.episode_number if slot else "",
        "title": idea.selected_title or "",
        "summary": idea.summary or "",
        "outline": idea.outline or [],
        "transcript": transcript_text,
    }

    # Fetch visual reference images from Drive if configured (best-effort)
    reference_images: list[dict] = []
    ref_folder_ids = config.get("referenceImageFolderIds") or []
    ref_file_ids = config.get("referenceImageFileIds") or []
    if ref_folder_ids or ref_file_ids:
        try:
            image_extensions = {"jpg", "jpeg", "png"}
            for folder_id in ref_folder_ids[:3]:
                try:
                    files = await list_folder_files(access_token, folder_id)
                    img_files = [
                        f for f in files
                        if f["name"].rsplit(".", 1)[-1].lower() in image_extensions
                    ]
                    for f in img_files[:3]:
                        b64, mime = await fetch_image_as_base64(access_token, f["id"])
                        reference_images.append({"data": b64, "mime_type": mime})
                except Exception:
                    pass
            for file_id in ref_file_ids[:4]:
                try:
                    b64, mime = await fetch_image_as_base64(access_token, file_id)
                    reference_images.append({"data": b64, "mime_type": mime})
                except Exception:
                    pass
            reference_images = reference_images[:8]
        except Exception:
            reference_images = []

    system_prompt, user_prompt = build_generate_art_direction_prompts(
        config, episode_data, has_reference_images=bool(reference_images)
    )

    try:
        text = await call_ai(
            system_prompt, user_prompt, config,
            images=reference_images if reference_images else None,
        )
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


# ---------------------------------------------------------------------------
# POST /api/ai/generate-episode-art
# ---------------------------------------------------------------------------


class GenerateEpisodeArtRequest(BaseModel):
    ideaId: str
    imagePrompt: str


@router.post("/ai/generate-episode-art")
async def generate_episode_art(
    body: GenerateEpisodeArtRequest,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    config = await get_config(db)

    if not config.get("openaiApiKey"):
        return JSONResponse(
            status_code=400,
            content={"error": "No OpenAI API key configured — DALL-E requires an OpenAI key"},
        )

    idea, slot = await get_idea_and_slot(db, body.ideaId)
    if idea is None:
        return JSONResponse(status_code=404, content={"error": "Idea not found"})
    if not slot or not slot.production_file_key:
        return JSONResponse(
            status_code=400,
            content={"error": "No production file key set on slot — cannot name the art file"},
        )

    filename = f"{slot.production_file_key}.png"

    # Generate image via DALL-E 3
    try:
        png_bytes = await call_dalle(body.imagePrompt, config)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            return JSONResponse(
                status_code=400,
                content={"error": "OpenAI rejected the prompt — try editing it"},
            )
        return JSONResponse(
            status_code=500, content={"error": f"DALL-E API error: {e}"}
        )
    except (httpx.RequestError, ValueError) as e:
        return JSONResponse(
            status_code=500, content={"error": f"DALL-E API error: {e}"}
        )

    # Get Drive access token
    settings = get_settings()
    if not all([
        settings.google_oauth_client_id,
        settings.google_oauth_client_secret,
        settings.google_oauth_refresh_token,
    ]):
        return JSONResponse(
            status_code=400,
            content={"error": "Google Drive OAuth not configured on server."},
        )

    cover_art_folder_id = config.get("gdriveFolderCoverArt")
    if not cover_art_folder_id:
        return JSONResponse(
            status_code=400,
            content={"error": "Cover art folder not configured — set gdriveFolderCoverArt in Config"},
        )

    try:
        access_token = await get_drive_access_token(
            settings.google_oauth_client_id,
            settings.google_oauth_client_secret,
            settings.google_oauth_refresh_token,
        )
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get Drive access token: {e}"},
        )

    # Delete old art file if it exists in asset inventory (regeneration case)
    inv = (slot.asset_inventory or {}) if slot else {}
    old_art = inv.get("album_art", {})
    if old_art.get("drive_file_id"):
        try:
            await delete_file(access_token, old_art["drive_file_id"])
        except (httpx.HTTPStatusError, httpx.RequestError):
            pass  # best-effort — old file may already be gone

    # Upload new PNG to Cover Art folder
    try:
        new_file_id = await upload_file_to_folder(
            access_token, cover_art_folder_id, filename, png_bytes
        )
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        return JSONResponse(
            status_code=500, content={"error": f"Failed to upload to Drive: {e}"}
        )

    # Persist Drive file ID on the idea
    await set_idea_image_file_id(db, body.ideaId, new_file_id)

    # Refresh asset inventory for this slot (best-effort)
    try:
        scan_config = {
            **config,
            "clientId": settings.google_oauth_client_id,
            "clientSecret": settings.google_oauth_client_secret,
            "refreshToken": settings.google_oauth_refresh_token,
        }
        new_inventory = await build_asset_inventory(
            slot.id, slot.production_file_key, scan_config
        )
        await set_asset_inventory(db, slot.id, new_inventory)
    except Exception:
        pass  # inventory refresh is best-effort; the upload succeeded

    return JSONResponse(content={"imageFileId": new_file_id, "filename": filename})
