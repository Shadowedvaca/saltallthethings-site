"""Prompt construction for AI proxy endpoints.

Replicates the exact prompt logic from js/ai-service.js so AI output is
consistent before and after migration.
"""

from __future__ import annotations

import json


def build_process_idea_prompts(config: dict, raw_notes: str) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt) for the process-idea endpoint."""
    segments = config.get("segments") or []
    segment_list = "\n".join(
        f"{i + 1}. {s['name']}{(' — ' + s['description']) if s.get('description') else ''}"
        for i, s in enumerate(segments)
    )
    title_count = config.get("titleCount") or 3
    show_context = config.get("showContext") or ""

    system_prompt = (
        f"{show_context}\n\n"
        "SHOW SEGMENTS (in order):\n"
        f"{segment_list}\n\n"
        "YOUR TASK:\n"
        "When given raw show notes/ideas from the host, you must return a JSON response with EXACTLY this structure "
        "(no markdown, no backticks, just pure JSON):\n\n"
        "{\n"
        '  "titles": ["Title Option 1", "Title Option 2", "Title Option 3"],\n'
        '  "summary": "A 2-3 sentence clean summary of what this episode is about.",\n'
        '  "outline": [\n'
        "    {\n"
        '      "segmentId": "opening",\n'
        '      "segmentName": "Opening Hook / Intro",\n'
        '      "talkingPoints": [\n'
        '        "First conversation prompt or topic to discuss",\n'
        '        "Second conversation prompt"\n'
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "RULES:\n"
        f"- Generate exactly {title_count} title options. Titles should be catchy, on-brand (salty, fun, WoW-themed), and hint at the main topic.\n"
        "- The summary should be clean and compelling — good enough for a podcast description.\n"
        "- The outline must include ALL segments listed above, in order.\n"
        "- Each segment should have 2-5 talking points that are natural conversation starters, not lecture bullets.\n"
        "- Talking points should be phrased as discussion prompts between two friends.\n"
        "- Return ONLY valid JSON. No explanation, no markdown fences, no preamble."
    )

    user_prompt = (
        f"Here are Rocket's raw notes for an upcoming episode. "
        f"Process these into the structured format:\n\n---\n{raw_notes}\n---"
    )

    return system_prompt, user_prompt


def build_generate_jokes_prompts(
    config: dict, used_jokes: list[str], theme_hint: str
) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt) for the generate-jokes endpoint."""
    joke_context = config.get("jokeContext") or ""
    joke_count = config.get("jokeCount") or 5

    used_list = "\n".join(f"- {j}" for j in used_jokes)
    used_section = (
        f"ALREADY USED JOKES (do NOT repeat these or anything too similar):\n{used_list}\n"
        if used_list
        else ""
    )

    system_prompt = (
        f"{joke_context}\n\n"
        f"{used_section}"
        "Return ONLY a JSON array of strings, each being one joke. "
        'No markdown, no backticks, no explanation. Example: ["joke one", "joke two"]\n'
        f"Generate exactly {joke_count} jokes."
    )

    user_prompt = (
        f"Generate salt jokes. Theme/topic hint for this batch: {theme_hint}"
        if theme_hint
        else "Generate a batch of general salt jokes for the show."
    )

    return system_prompt, user_prompt


def build_generate_art_direction_prompts(
    config: dict, episode_data: dict, has_reference_images: bool = False
) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt) for the generate-art-direction endpoint."""
    style_bible = config.get("artStyleBible") or {}
    archetypes = config.get("artArchetypes") or []
    art_log = config.get("artLog") or []
    recent_log = art_log[-5:]

    style_bible_text = json.dumps(style_bible, indent=2)
    archetypes_text = json.dumps(archetypes, indent=2)

    continuity_section = ""
    if recent_log:
        continuity_section = (
            "\n\nRECENT EPISODE ART LOG (last 5 — for variety, avoid repeating):\n"
            + json.dumps(recent_log, indent=2)
            + "\n\nCONTINUITY RULES:\n"
            "- Do NOT repeat the same archetype as either of the last 2 episodes.\n"
            "- Do NOT repeat the same environment setting as either of the last 2 episodes.\n"
            "- Do NOT repeat the same baby gag as any of the last 3 episodes.\n"
        )

    reference_style_desc = config.get("referenceStyleDescription") or ""

    reference_images_section = ""
    if has_reference_images:
        reference_images_section = (
            "\n\nREFERENCE IMAGES: Visual brand reference images have been attached. "
            "Study them carefully. The images show the EXACT character designs, rendering style, "
            "and aesthetic that ALL generated art must match. These override any text description. "
            "Your finalImagePrompt must describe what you see in these images precisely enough "
            "for DALL-E to reproduce the same style."
        )

    reference_style_section = ""
    if reference_style_desc:
        reference_style_section = (
            "\n\nVISUAL STYLE ANALYSIS (from reference images — treat as ground truth):\n"
            f"{reference_style_desc}"
        )

    system_prompt = (
        "You are an art director for the Salt All The Things World of Warcraft podcast.\n\n"
        "STYLE BIBLE:\n"
        f"{style_bible_text}\n\n"
        "VISUAL ARCHETYPES:\n"
        f"{archetypes_text}"
        f"{reference_style_section}"
        f"{continuity_section}"
        f"{reference_images_section}\n\n"
        "YOUR TASK:\n"
        "Analyze the episode and produce a complete art direction plan. "
        "Return ONLY valid JSON with EXACTLY this structure (no markdown, no backticks, just pure JSON):\n\n"
        "{\n"
        '  "topics": ["topic A", "topic B", "topic C"],\n'
        '  "tone": "excited and funny",\n'
        '  "archetype": {\n'
        '    "id": "delve_expedition",\n'
        '    "name": "Delve / Cave Expedition",\n'
        '    "reason": "Episode centers on exploration and speculation about new zones"\n'
        '  },\n'
        '  "environment": "ancient labyrinth with glowing runes and collapsed archways",\n'
        '  "bigElementalRole": "stands at the entrance as expedition leader, torch in hand",\n'
        '  "babyGags": [\n'
        '    "one baby reading the map upside down",\n'
        '    "one baby clinging to the arm salt-scared"\n'
        '  ],\n'
        '  "props": ["bronze microphone", "salt shaker", "lantern"],\n'
        '  "sceneSummary": "Labyrinth entrance scene: the big salt elemental leads the expedition while baby elementals cause comedic chaos",\n'
        '  "finalImagePrompt": "Square 1024x1024 fantasy digital painting in World of Warcraft style. Scene: ..."\n'
        "}\n\n"
        "FINAL IMAGE PROMPT STRUCTURE — the finalImagePrompt must be a complete, ready-to-send DALL-E "
        "prompt combining:\n"
        "1. Format and art style from the style bible\n"
        "2. Scene summary\n"
        "3. Character descriptions (big elemental + baby elementals) from style bible\n"
        "4. Baby gags as action descriptions\n"
        "5. Props list\n"
        "6. Environment details\n"
        "7. Lighting from style bible\n"
        "8. All rules from style bible (no text in image, no real people, etc.)\n\n"
        "CRITICAL: finalImagePrompt MUST be under 3800 characters. Be concise — "
        "dense specific description beats verbose repetition. Summarize rules rather than quoting them verbatim.\n\n"
        "Return ONLY valid JSON. No explanation, no markdown fences, no preamble."
    )

    transcript = episode_data.get("transcript") or ""
    if len(transcript) > 6000:
        transcript = transcript[:6000] + "\n[transcript truncated]"

    outline_text = json.dumps(episode_data.get("outline") or [], indent=2)

    user_prompt = (
        f"Episode: {episode_data.get('episodeNumber', '')} — {episode_data.get('title', '')}\n\n"
        f"Summary:\n{episode_data.get('summary', '')}\n\n"
        f"Outline:\n{outline_text}\n\n"
        f"Transcript excerpt:\n{transcript}\n\n"
        "Analyze this episode and return the art direction JSON."
    )

    return system_prompt, user_prompt
