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
    archetypes = config.get("artArchetypes") or []
    art_log = config.get("artLog") or []
    recent_log = art_log[-5:]

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

    reference_images_section = ""
    if has_reference_images:
        reference_images_section = (
            "\n\nREFERENCE IMAGES ATTACHED: The images provided show the exact visual brand. "
            "Study them before writing the scene prompt — the characters, style, and aesthetic "
            "in those images are the ground truth. Your scene prompt must describe that style."
        )

    system_prompt = (
        "You are generating episode artwork for the podcast 'Salt All The Things' — "
        "a World of Warcraft podcast. Reference images defining the visual brand are attached.\n\n"
        "OUR VISUAL IDENTITY:\n"
        "- Main characters are salt elementals — crystalline ice-blue rock creatures with glowing "
        "blue eyes, jagged salt crystal spikes, and bronze/gold armor bands and pauldrons\n"
        "- There's a BIG salt elemental (the main mascot, imposing, broad-shouldered) and "
        "BABY salt elementals (small, chibi-proportioned, expressive, mischievous little guys)\n"
        "- Recurring props: a vintage bronze podcast microphone, glass salt shakers with metal lids, "
        "tipped-over salt shakers pouring glowing salt\n"
        "- Art style: digital painting, rich saturated colors, WoW-inspired fantasy aesthetic — "
        "think Blizzard cinematic concept art crossed with illustrated podcast branding\n"
        "- Color palette: icy blues and whites for the elementals, deep navy/purple/black backgrounds, "
        "warm gold and bronze metallics for accents, orange fire/torch lighting for warmth contrast\n"
        "- Environments are WoW-style: tavern interiors, cave hideouts, forge rooms, treasure hoards "
        "— dark atmospheric spaces with dramatic rim lighting\n"
        "- Mood: playful but epic, funny but cool-looking — the baby salts bring humor, "
        "the big elemental brings gravitas\n\n"
        "RULES FOR ALL GENERATED IMAGES:\n"
        "- Always feature salt elementals (big one, baby ones, or both) as the characters\n"
        "- Never include real people, recognizable WoW characters by name, or any text/words\n"
        "- Keep the dark moody background with warm accent lighting\n"
        "- Props and environments should reference the episode's topics in creative visual ways\n"
        "- The baby salt elementals should be doing something funny or expressive related to the topic\n\n"
        "VISUAL ARCHETYPES (use these to pick the scene type):\n"
        f"{archetypes_text}"
        f"{continuity_section}"
        f"{reference_images_section}\n\n"
        "YOUR TASK:\n"
        "Read the episode info and return a JSON art direction plan. "
        "Return ONLY valid JSON with EXACTLY this structure (no markdown, no backticks):\n\n"
        "{\n"
        '  "topics": ["topic A", "topic B", "topic C"],\n'
        '  "tone": "excited and funny",\n'
        '  "archetype": {\n'
        '    "id": "tavern_talk",\n'
        '    "name": "Tavern Talk",\n'
        '    "reason": "General discussion episode — hosts debating patch changes over drinks"\n'
        '  },\n'
        '  "environment": "cozy tavern interior, stone walls, warm torchlight, wooden barrels",\n'
        '  "bigElementalRole": "looming behind the bar, arms crossed, looking unimpressed",\n'
        '  "babyGags": [\n'
        '    "one baby dramatically spilling salt onto the bar",\n'
        '    "one baby arguing with a tiny patch note scroll"\n'
        '  ],\n'
        '  "props": ["bronze microphone on the bar", "overflowing salt shaker", "patch note scroll"],\n'
        '  "sceneSummary": "Tavern debate: the big salt elemental presides over the bar while babies cause chaos reacting to the week\'s patch notes",\n'
        '  "finalImagePrompt": "Scene prompt describing what to paint — characters, action, environment, props, lighting. Concise but specific."\n'
        "}\n\n"
        "The finalImagePrompt is the scene description only — style, characters, and rules will be "
        "added separately. Just describe: what is happening, where, who is doing what, with what props.\n\n"
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
