"""Prompt construction for AI proxy endpoints.

Replicates the exact prompt logic from js/ai-service.js so AI output is
consistent before and after migration.
"""

from __future__ import annotations


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
