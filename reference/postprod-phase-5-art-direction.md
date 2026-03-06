# Post-Production Phase 5 — AI Art Direction

## Goal

Add AI-powered art direction to the post-production tab. Given an episode's title,
summary, outline, and transcript, the AI analyzes the episode, selects a visual
archetype, and builds a complete image generation prompt. The user reviews and approves
the concept before image generation.

This phase produces the text output only — the prompt and scene plan. Image generation
(DALL-E / OpenAI) is Phase 6.

---

## Context

Read before starting:
- `reference/ChatGPT-reference.md` — full art system spec (sections 7–14)
- `reference/ChatGPT-art-book.txt` — the brand bible and archetype definitions
- `reference/postprod-phase-3-ui.md` — post-production tab where the button lives
- `CLAUDE.md` — AI proxy pattern (httpx only, no SDKs), prompts.py, ai_client.py

### How the existing AI proxy works

All AI calls go through:
- `src/satt/prompts.py` — builds system + user prompts
- `src/satt/ai_client.py` — `call_ai()` dispatches to Claude or OpenAI via httpx
- `src/satt/routes/ai.py` — FastAPI endpoints that wire them together

This phase adds to all three files following the exact same pattern.

### Transcript availability

The transcript `.txt` file lives in Google Drive. The server cannot read it directly.
Two options:
1. The user pastes/uploads the transcript text when requesting art direction
2. The transcript text is stored in the DB

For Phase 5, use option 1: the frontend fetches the transcript text and sends it in
the request body. This avoids new DB columns and keeps the scope tight.

The frontend JS can fetch the transcript file from Google Drive using the Drive file ID
stored in `asset_inventory.transcript_txt.drive_file_id` and the standard Google Drive
export URL pattern. No auth needed for files shared within the org's Drive.

---

## Style Bible and Archetypes (Config)

These are stored in `satt.config` as JSONB (no migration needed).

### `artStyleBible` (default value to seed)

```json
{
  "format": "square 1024x1024",
  "artStyle": "World of Warcraft inspired fantasy digital painting, painterly, cinematic",
  "characters": {
    "bigElemental": "large crystalline salt elemental, broad-shouldered and imposing, glowing cyan eyes, bronze and gold armor accents, icy blue crystal body with jagged spikes",
    "babyElementals": "small chibi salt elementals, mischievous and expressive, same material language as the big elemental but tiny and comedic"
  },
  "props": ["vintage bronze microphone", "salt shaker", "glowing spilled salt"],
  "lighting": "dark moody background, cool blue character highlights, warm orange torch or fire accents, high contrast cinematic rim light",
  "palette": ["icy blue", "navy", "deep purple", "bronze", "gold", "warm orange torchlight"],
  "rules": ["no text or words in image", "no real people", "square composition readable at thumbnail size", "dark moody background always present"]
}
```

### `artArchetypes` (default value to seed)

```json
[
  {
    "id": "tavern_talk",
    "name": "Tavern Talk",
    "useFor": ["general discussion", "opinion episodes", "patch reactions", "community talk"],
    "scene": "tavern or podcast set, microphone on table, big elemental as host behind, baby elementals acting out jokes around the table"
  },
  {
    "id": "delve_expedition",
    "name": "Delve / Cave Expedition",
    "useFor": ["exploration", "new zones", "systems discussion", "speculation", "lore-heavy"],
    "scene": "cave, ruins, labyrinth, or treasure chamber, big elemental as guide or guardian, babies exploring, arguing over a map, pulling a wagon, triggering traps"
  },
  {
    "id": "raid_chaos",
    "name": "Raid / Battle Chaos",
    "useFor": ["class balance", "boss discussion", "raid prep", "major patch or expansion launch"],
    "scene": "dramatic combat-ready scene, big elemental in dominant action pose, babies panicking, cheering, casting, carrying loot, spilling salt everywhere"
  },
  {
    "id": "workshop_build",
    "name": "Workshop / Build Room",
    "useFor": ["housing", "crafting", "UI or tools", "guild infrastructure", "planning episodes"],
    "scene": "forge room, workshop, construction site, or blueprint table, babies building, hammering, misplacing things, big elemental supervising or facepalming"
  },
  {
    "id": "lore_vision",
    "name": "Lore Vision / Cosmic Tension",
    "useFor": ["light vs void", "story speculation", "character arcs", "philosophical discussion"],
    "scene": "dramatic magical environment, split lighting blue void vs gold light, big elemental caught between forces, babies reacting to magical phenomena in funny ways"
  },
  {
    "id": "auction_house",
    "name": "Auction House / Town Comedy",
    "useFor": ["economy", "professions", "farming", "mounts", "collectibles", "side content"],
    "scene": "market stall, treasure room, cluttered guild hall, mailboxes, item piles, babies selling, hoarding, sorting, fighting over loot, big elemental as merchant or banker"
  }
]
```

These defaults should be seeded into the DB config on first use if not already present.
The Config page (future) can expose editing for advanced users. For Phase 5, they are
read-only from the DB.

---

## `src/satt/prompts.py` Addition

Add `build_generate_art_direction_prompts(config, episode_data)`:

```python
def build_generate_art_direction_prompts(config: dict, episode_data: dict) -> tuple[str, str]:
```

Where `episode_data` contains:
```python
{
    "episodeNumber": "EP001",
    "title": "War Within Seasons Ranked",
    "summary": "...",
    "outline": [...],  # the segments and talking points
    "transcript": "..."  # full text, may be long — truncate to ~6000 chars if needed
}
```

**System prompt** must include:
1. The `artStyleBible` (character rules, style rules, props, lighting)
2. All `artArchetypes` with their `useFor` tags and scene descriptions
3. The `artLog` (last 5 entries) — "recent episode art used, do not repeat these"
4. Instructions to return strict JSON with this exact shape:

```json
{
  "topics": ["topic A", "topic B", "topic C"],
  "tone": "excited and funny",
  "archetype": {
    "id": "delve_expedition",
    "name": "Delve / Cave Expedition",
    "reason": "Episode centers on exploration and speculation about new zones"
  },
  "environment": "ancient labyrinth with glowing runes and collapsed archways",
  "bigElementalRole": "stands at the entrance as expedition leader, torch in hand",
  "babyGags": [
    "one baby reading the map upside down",
    "one baby clinging to the big elemental's arm salt-scared",
    "one baby holding a tiny mining pick and looking very determined"
  ],
  "props": ["bronze microphone", "treasure map", "salt shaker", "lantern"],
  "sceneSummary": "Labyrinth entrance scene: the big salt elemental leads the expedition while baby elementals cause comedic chaos around him",
  "finalImagePrompt": "..."
}
```

**User prompt**: episode number, title, summary, key outline points, and transcript
excerpt. Ask it to analyze and produce art direction.

The `finalImagePrompt` field in the output must be the complete, ready-to-send DALL-E
prompt assembled from style bible + archetype + scene specifics. See
`ChatGPT-reference.md` section 13 for the prompt structure.

---

## `src/satt/routes/ai.py` Addition

### Request model

```python
class GenerateArtDirectionRequest(BaseModel):
    ideaId: str
    transcriptText: str = ""
```

### Endpoint

```
POST /api/ai/generate-art-direction
```

Requires JWT auth.

Behavior:
1. Load config — validate AI key and art config present
2. Load the idea and its slot (for episode number)
3. Build `episode_data` dict from idea + slot + request transcript
4. Call `build_generate_art_direction_prompts(config, episode_data)`
5. Call `call_ai(system_prompt, user_prompt, config)`
6. Parse JSON response (same defensive stripping as existing endpoints)
7. If `artLog` update: append this episode to `config.artLog` and save config
8. Return the parsed art direction object

### Response

```json
{
  "topics": [...],
  "tone": "...",
  "archetype": { "id": "...", "name": "...", "reason": "..." },
  "environment": "...",
  "bigElementalRole": "...",
  "babyGags": [...],
  "props": [...],
  "sceneSummary": "...",
  "finalImagePrompt": "..."
}
```

---

## Art Continuity Log (`artLog`)

After each successful art direction call, append to `satt.config.artLog`:

```json
{
  "episodeNum": 42,
  "episodeNumber": "EP042",
  "archetypeId": "delve_expedition",
  "environment": "labyrinth cave with glowing runes",
  "babyGags": ["map reading", "salt-scared"],
  "props": ["microphone", "salt shaker", "treasure map"],
  "generatedAt": "2026-03-06T14:00:00Z"
}
```

Include in the system prompt: last 5 artLog entries with instruction to avoid
repeating the same archetype within the last 2 episodes, same environment within
the last 2 episodes, same baby gag within the last 3 episodes.

Cap the artLog at 50 entries (drop oldest) to keep the config blob manageable.

---

## Post-Production Tab UI Addition (Phase 3 extension)

Add "Generate Art Direction" button to each episode row where:
- `transcript_txt.present == true`
- `album_art.present == false` (or user wants to regenerate)

On click:
1. Fetch the transcript from Google Drive using the `drive_file_id` from asset_inventory:
   - URL: `https://drive.google.com/uc?export=download&id={drive_file_id}`
   - This is a direct download of the file content
2. Send `POST /api/ai/generate-art-direction` with `ideaId` and `transcriptText`
3. Show a loading state (this takes several seconds)
4. On success, display the art direction panel below the row:
   - Archetype chosen + reason
   - Scene summary
   - Baby gags list
   - Final image prompt (copyable text area)
   - "Generate Art" button (Phase 6)

The final image prompt text area should be editable — the user can tweak it before
sending to image generation.

---

## Tests

Add to `src/satt/tests/test_ai.py`:
- `POST /api/ai/generate-art-direction` returns correct shape with mocked AI response
- `artLog` is updated in config after successful call
- Missing transcript text returns 422
- Missing AI key returns 400
- Continuity rules are included in system prompt when artLog has entries

---

## Deliverables Checklist

- [ ] Default `artStyleBible` seeded to `satt.config` if not present
- [ ] Default `artArchetypes` seeded to `satt.config` if not present
- [ ] `build_generate_art_direction_prompts()` added to `prompts.py`
- [ ] Style bible, archetypes, and last-5 artLog entries all in system prompt
- [ ] `POST /api/ai/generate-art-direction` endpoint implemented
- [ ] Response JSON parsed and validated
- [ ] artLog updated and capped at 50 after each call
- [ ] "Generate Art Direction" button added to postproduction.html
- [ ] Transcript fetched from Drive file ID before calling endpoint
- [ ] Art direction panel displayed on success (archetype, summary, gags, prompt)
- [ ] Final image prompt text area is editable
- [ ] Tests pass

---

## What This Phase Does NOT Include

- Image generation (Phase 6)
- Uploading art to Google Drive
- Storing image_file_id on the idea
