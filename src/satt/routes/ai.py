"""AI proxy endpoints — all require authentication."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from satt.ai_client import call_ai, call_dalle, call_gpt_image_1
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

_ART_STYLE_BIBLE_VERSION = 3

_DEFAULT_ART_STYLE_BIBLE: dict = {
    "version": _ART_STYLE_BIBLE_VERSION,
    "format": "square 1024x1024",
    "artStyle": (
        "3D rendered digital illustration with hand-painted texture detail. "
        "Stylized fantasy-game aesthetic — think polished indie game art with cinematic lighting. "
        "NOT painterly or 2D. Characters are dimensional, faceted, and physically solid."
    ),
    "characters": {
        "bigElemental": (
            "LARGE crystalline salt elemental — compact, squat, chibi-proportioned (large head relative to body). "
            "Body made of geometric, faceted icy-blue salt crystals — angular planes and beveled edges, "
            "semi-translucent in places with light catching on crystal surfaces. "
            "Bright cyan/electric blue glowing eyes (almond-shaped). "
            "Jagged crystalline crown of 3–5 spikes on top of head. "
            "Large mischievous grin with prominent teeth — evil but playful expression. "
            "Chunky blocky limbs with segmented armor plating. "
            "Gold/bronze spiked shoulder pauldrons and waist belt. "
            "Dark blue-gray scale-like chest armor contrasting with icy body. "
            "NOT a human, bear, or animal — a crystal salt creature."
        ),
        "babyElementals": (
            "SMALL chibi salt elementals — identical crystal material and design as the big elemental "
            "but tiny (roughly 1/3 the height). Same faceted icy-blue crystal body, same evil grin, "
            "same glowing cyan eyes, same gold armor accents. Oversized expressive faces. "
            "NOT humans, bears, or animals — miniature crystal salt creatures matching the big elemental's style exactly."
        ),
    },
    "props": [
        "tall chrome/stainless steel salt shaker with domed perforated top and brass/gold detailing",
        "vintage art-deco podcast microphone — brass/gold ribbed body, large spherical mesh top, weighted stand base",
        "spilled salt granules and glowing cyan salt particle trails",
    ],
    "lighting": (
        "warm orange/amber rim lighting from torches or fire behind characters for contrast, "
        "cool cyan fill light from the characters' own crystal glow, "
        "sharp specular highlights on faceted crystal edges, deep shadow in backgrounds"
    ),
    "palette": [
        "icy blue (#5B9FD9 to #7FBAE0) — character bodies",
        "electric cyan (#00D4FF to #00E5FF) — eye glow and magic effects",
        "gold/bronze (#D4A574 to #C97A3D) — armor, props, microphone",
        "deep navy/purple-black (#1A1A2E, #16213E) — backgrounds",
        "warm amber/orange (#D4794C) — environmental torch lighting",
    ],
    "rules": [
        "NO text, words, letters, or numbers anywhere in the image",
        "characters must be crystalline salt creatures — NOT humans, NOT bears, NOT animals",
        "3D rendered style — dimensional, faceted, not flat or painted",
        "square composition readable at thumbnail size",
        "dark moody background always present",
        "baby elementals must look like miniature versions of the big elemental",
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

    # Art direction always uses OpenAI (GPT-4o) — it feeds DALL-E and vision works best in-ecosystem
    if not config.get("openaiApiKey"):
        return JSONResponse(
            status_code=400,
            content={"error": "No API key configured — art direction requires an OpenAI key (GPT-4o)"},
        )
    art_config = {**config, "aiModel": "openai"}

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
    ref_image_errors: list[str] = []
    ref_folder_ids = config.get("referenceImageFolderIds") or []
    ref_file_ids = config.get("referenceImageFileIds") or []
    if ref_folder_ids or ref_file_ids:
        image_extensions = {"jpg", "jpeg", "png"}
        for folder_id in ref_folder_ids[:3]:
            try:
                files = await list_folder_files(access_token, folder_id)
                img_files = [
                    f for f in files
                    if f["name"].rsplit(".", 1)[-1].lower() in image_extensions
                ]
                for f in img_files[:3]:
                    try:
                        b64, mime = await fetch_image_as_base64(access_token, f["id"])
                        reference_images.append({"data": b64, "mime_type": mime})
                    except Exception as e:
                        ref_image_errors.append(f"image {f['name']}: {e}")
            except Exception as e:
                ref_image_errors.append(f"folder {folder_id}: {e}")
        for file_id in ref_file_ids[:4]:
            try:
                b64, mime = await fetch_image_as_base64(access_token, file_id)
                reference_images.append({"data": b64, "mime_type": mime})
            except Exception as e:
                ref_image_errors.append(f"file {file_id}: {e}")
        reference_images = reference_images[:8]

    system_prompt, user_prompt = build_generate_art_direction_prompts(
        config, episode_data, has_reference_images=bool(reference_images)
    )

    try:
        text = await call_ai(
            system_prompt, user_prompt, art_config,
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

    # Upload art direction JSON to Cover Art Drive folder (best-effort)
    cover_art_folder_id = config.get("gdriveFolderCoverArt")
    if cover_art_folder_id and slot and slot.production_file_key:
        try:
            art_json_filename = f"{slot.production_file_key}_artdirection.json"
            art_json_bytes = json.dumps(result, indent=2).encode()

            # Delete old art direction JSON if present
            inv = (slot.asset_inventory or {})
            old_art_dir = inv.get("art_direction", {})
            if old_art_dir.get("drive_file_id"):
                try:
                    await delete_file(access_token, old_art_dir["drive_file_id"])
                except Exception:
                    pass

            new_art_dir_id = await upload_file_to_folder(
                access_token, cover_art_folder_id, art_json_filename,
                art_json_bytes, mime_type="application/json",
            )

            # Patch asset inventory with new art_direction entry
            inv["art_direction"] = {
                "present": True,
                "drive_file_id": new_art_dir_id,
                "modified": datetime.now(timezone.utc).isoformat(),
            }
            await set_asset_inventory(db, slot.id, inv)
        except Exception:
            pass  # best-effort — art direction itself succeeded

    response_data = dict(result)
    if ref_image_errors:
        response_data["referenceImageWarnings"] = ref_image_errors
    response_data["referenceImagesLoaded"] = len(reference_images)

    return JSONResponse(content=response_data)


# ---------------------------------------------------------------------------
# POST /api/ai/analyze-reference-style
# ---------------------------------------------------------------------------


@router.post("/ai/analyze-reference-style")
async def analyze_reference_style(
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Ask GPT-4o to describe the visual style of the reference images and save to config.

    The saved description is injected into every future art direction prompt as ground truth,
    so GPT-4o doesn't have to rediscover the style from images each time.
    """
    config = await get_config(db)

    if not config.get("openaiApiKey"):
        return JSONResponse(
            status_code=400,
            content={"error": "No OpenAI API key configured"},
        )

    ref_folder_ids = config.get("referenceImageFolderIds") or []
    ref_file_ids = config.get("referenceImageFileIds") or []
    if not ref_folder_ids and not ref_file_ids:
        return JSONResponse(
            status_code=400,
            content={"error": "No reference image folder or file IDs configured"},
        )

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

    try:
        access_token = await get_drive_access_token(
            settings.google_oauth_client_id,
            settings.google_oauth_client_secret,
            settings.google_oauth_refresh_token,
        )
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        return JSONResponse(status_code=500, content={"error": f"Failed to get Drive token: {e}"})

    reference_images: list[dict] = []
    image_extensions = {"jpg", "jpeg", "png"}
    for folder_id in ref_folder_ids[:3]:
        try:
            files = await list_folder_files(access_token, folder_id)
            img_files = [f for f in files if f["name"].rsplit(".", 1)[-1].lower() in image_extensions]
            for f in img_files[:3]:
                try:
                    b64, mime = await fetch_image_as_base64(access_token, f["id"])
                    reference_images.append({"data": b64, "mime_type": mime})
                except Exception:
                    pass
        except Exception:
            pass
    for file_id in ref_file_ids[:4]:
        try:
            b64, mime = await fetch_image_as_base64(access_token, file_id)
            reference_images.append({"data": b64, "mime_type": mime})
        except Exception:
            pass
    reference_images = reference_images[:8]

    if not reference_images:
        return JSONResponse(
            status_code=400,
            content={"error": "No reference images could be loaded from the configured IDs"},
        )

    system_prompt = (
        "You are describing a visual brand for an image generation system. "
        "Write in plain, dense prose — no headers, no bullet points, no markdown. "
        "Every sentence should be something that directly helps an image model reproduce this style."
    )
    user_prompt = (
        "These are reference images for the podcast 'Salt All The Things.' "
        "Study them carefully and write a single paragraph (no headers, no lists) that captures:\n\n"
        "- What the characters are made of, how they look, what makes them instantly recognizable\n"
        "- The exact art style — rendering technique, level of detail, finish\n"
        "- Color palette and lighting approach\n"
        "- Recurring props and how they appear\n"
        "- Anything a model must know to NOT get wrong (common misinterpretations to rule out)\n\n"
        "Write it the way you'd brief a freelance illustrator in one paragraph — "
        "specific, practical, zero fluff. This will be injected directly into an AI art direction prompt."
    )

    art_config = {**config, "aiModel": "openai"}
    try:
        description = await call_ai(system_prompt, user_prompt, art_config, images=reference_images)
    except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
        return JSONResponse(status_code=500, content={"error": f"AI API error: {e}"})

    config["referenceStyleDescription"] = description
    await save_config(db, config)

    return JSONResponse(content={"description": description, "imagesAnalyzed": len(reference_images)})


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

    # Get Drive access token (needed for both reference images and upload)
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

    # Generate image via gpt-image-1
    continuity_prefix = "Same art style and characters as previous Salt All The Things artwork. "
    final_prompt = continuity_prefix + body.imagePrompt
    try:
        png_bytes = await call_gpt_image_1(final_prompt, config)
    except httpx.HTTPStatusError as e:
        try:
            openai_error = e.response.json()
            openai_msg = (
                openai_error.get("error", {}).get("message")
                or openai_error.get("message")
                or str(e)
            )
        except Exception:
            openai_msg = str(e)
        return JSONResponse(
            status_code=e.response.status_code,
            content={"error": f"OpenAI error: {openai_msg}"},
        )
    except (httpx.RequestError, ValueError) as e:
        return JSONResponse(status_code=500, content={"error": f"Image generation error: {e}"})

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
