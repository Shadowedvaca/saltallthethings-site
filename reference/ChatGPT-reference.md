Great — I read your answers and they’re clear enough to produce a **clean reference spec Claude Code can consume**.

I’m including your file as the authoritative context so Claude knows what it is building against:


Below is the **Markdown spec you asked for**. This only covers the **ChatGPT / AI pieces and workflow structure**. Claude Code can then combine this with your existing backend and the local scan agent.

---

# SATT Post-Production Workflow — AI & Art System Reference

This document describes the **AI-driven components and workflow** for the Salt All The Things post-production system.

It assumes the current application state described in:

**ChatGPT-Answers.md**


This spec only defines:

* the **episode art generation pipeline**
* the **AI prompt structures**
* the **API contracts**
* the **continuity tracking**
* the **data needed for the UI**

Claude Code will implement the surrounding infrastructure.

---

# 1. Post-Production System Overview

This feature introduces a **new workflow separate from show planning**.

Existing workflow:

```
Idea creation → AI processing → Scheduling → Recording
```

New workflow:

```
Recording → Raw Audio → Transcript → Album Art → Release
```

The new **Post-Production tab** manages the latter.

The tab shows a **queue of recorded episodes** and tracks asset status.

Assets tracked:

| Asset             | Source        |
| ----------------- | ------------- |
| Raw Dog Recording | uploaded WAV  |
| Finished Show     | edited MP3    |
| Transcript        | WhisperX      |
| Album Art         | AI generation |

The app does **not access files directly**.

Instead a **local scan agent pushes metadata**.

---

# 2. Post-Production Queue Logic

Episodes shown when:

```
ShowSlot.record_date <= today
```

Sorted:

```
ORDER BY record_date DESC
```

Each row represents:

```
ShowSlot + Idea
```

Displayed fields:

| Column         | Source                       |
| -------------- | ---------------------------- |
| Episode Number | ShowSlot                     |
| Episode Title  | Idea                         |
| Record Date    | ShowSlot                     |
| Raw Audio      | asset inventory              |
| Finished Audio | asset inventory              |
| Transcript     | asset inventory              |
| Album Art      | asset inventory              |
| Production Key | ShowSlot.production_file_key |
| Next Step      | computed                     |

---

# 3. Canonical Filename System

Each episode has:

```
production_file_key
```

Example:

```
SATT-EP042
```

All asset lookups derive from this key.

Example resolution:

```
Raw audio:
SATT-EP042.wav

Finished audio:
SATT-EP042.mp3

Transcript:
SATT-EP042.txt

Album art:
SATT-EP042.png
```

The UI allows editing the key.

This resolves most asset matching issues.

---

# 4. Asset Inventory System

The server never accesses Google Drive.

A **local watcher agent** scans folders and sends metadata.

Example payload:

```
POST /api/assets/inventory
```

```
{
  "episodes": [
    {
      "production_file_key": "SATT-EP042",
      "raw_audio": {
        "present": true,
        "modified": "2026-03-01T18:22:00Z"
      },
      "finished_audio": {
        "present": false
      },
      "transcript": {
        "present": true,
        "modified": "2026-03-01T19:05:00Z"
      },
      "album_art": {
        "present": false
      }
    }
  ]
}
```

Server stores this metadata.

UI reads only from stored metadata.

---

# 5. Transcript Staleness Logic

Transcript is stale if:

```
audio.modified > transcript.modified
```

If stale:

```
Transcript status = "STALE"
```

This signals the watcher to rerun transcription.

---

# 6. Album Art Generation Pipeline

Album art generation occurs after transcript exists.

Pipeline:

```
Transcript → AI analysis → Art direction → Image prompt → Image generation
```

Two endpoints exist:

```
generate-art-direction
generate-episode-art
```

---

# 7. Episode Art Direction System

Art direction determines:

* scene concept
* visual archetype
* props
* characters
* final image prompt

---

# 8. Style Bible (Config)

Stored in:

```
satt.config.artStyleBible
```

Example:

```
{
  "brand": "Salt All The Things",
  "format": "square 1024x1024",
  "characters": {
    "bigElemental": "large crystalline salt elemental with glowing blue eyes and bronze armor",
    "babyElementals": "small chibi salt elementals used for comedic action"
  },
  "style": [
    "digital fantasy painting",
    "World of Warcraft inspired",
    "dramatic lighting",
    "cinematic composition"
  ],
  "palette": [
    "icy blues",
    "navy",
    "purple",
    "bronze",
    "torchlight orange"
  ],
  "rules": [
    "no text in image",
    "no real people",
    "must include salt elementals",
    "dark moody background"
  ]
}
```

---

# 9. Art Archetypes

Stored in:

```
satt.config.artArchetypes
```

Examples:

### Tavern Talk

Use for general discussion episodes.

Scene pattern:

```
microphone on table
baby elementals acting around it
big elemental behind
```

---

### Delve Expedition

Use for exploration or speculation episodes.

Scene pattern:

```
cave / labyrinth
map reading
treasure
lanterns
```

---

### Raid Chaos

Use for raid or combat topics.

Scene pattern:

```
battle stance
magic effects
loot chaos
```

---

### Workshop Build

Use for housing / crafting topics.

Scene pattern:

```
blueprints
construction
tools
```

---

### Lore Vision

Use for deep lore discussions.

Scene pattern:

```
cosmic magic
light vs void
prophecy imagery
```

---

# 10. AI Art Direction Endpoint

```
POST /api/ai/generate-art-direction
```

Input:

```
{
  "ideaId": 123
}
```

Server retrieves:

* title
* summary
* outline
* transcript
* recent art log

---

### Output

```
{
  "topics": [],
  "tone": [],
  "archetype": {
    "id": "",
    "reason": ""
  },
  "environment": "",
  "bigElementalRole": "",
  "babyGags": [],
  "props": [],
  "sceneSummary": "",
  "finalImagePrompt": ""
}
```

---

# 11. Image Generation Endpoint

```
POST /api/ai/generate-episode-art
```

Input:

```
{
  "ideaId": 123,
  "prompt": "image prompt"
}
```

Output:

```
{
  "image_file_id": "google_drive_file_id"
}
```

Stored on:

```
Idea.image_file_id
```

---

# 12. Art Continuity Log

Stored in:

```
satt.config.artLog
```

Example entry:

```
{
  "episode": 42,
  "archetype": "delve_expedition",
  "environment": "labyrinth cave",
  "babyGags": ["map reading","spilled salt"],
  "props": ["microphone","salt shaker"]
}
```

Used to prevent repetition.

Rules:

Avoid repeating:

```
same archetype within last 2 episodes
same environment within last 2 episodes
same gag within last 3 episodes
```

---

# 13. Final Image Prompt Builder

The final prompt must combine:

```
style bible
scene summary
props
lighting
rules
```

Example prompt structure:

```
Square 1024x1024 fantasy digital painting.

World of Warcraft inspired art style.

Scene: {sceneSummary}

Characters:
Large crystalline salt elemental with glowing blue eyes and bronze armor.

Baby salt elementals performing comedic actions:
{babyGags}

Props:
{props}

Environment:
{environment}

Lighting:
dark moody cave with warm torchlight and cool magical rim lighting.

No text or words in image.
```

---

# 14. UI Flow

User actions:

```
1 Generate Art Direction
2 Review scene concept
3 Generate Episode Art
4 Approve or regenerate
```

Display fields:

```
Archetype
Scene Summary
Prompt
Image Preview
```

---

# 15. Interaction With Local Watcher

Watcher responsibilities:

```
transcription
folder scanning
asset metadata push
```

Watcher triggers:

```
new raw audio → transcribe
new finished audio → retranscribe
```

Server responsibilities:

```
store metadata
display queue
generate art
```

---

# 16. Post-Production Status Logic

Next step logic:

```
Raw missing → Upload raw audio
Transcript missing → Run transcription
Transcript stale → Re-transcribe
Art missing → Generate art
Finished audio present → Ready to publish
```

---

# 17. Long-Term Extension Ideas

Future features may include:

```
auto-upload album art to Google Drive
auto-publish to Spotify
episode completion tracking
AI thumbnail variants
```

---

# 18. Implementation Priority

Recommended build order:

### Phase 1

Post-production tab
Asset inventory endpoint

### Phase 2

AI art direction endpoint

### Phase 3

Image generation endpoint

### Phase 4

continuity tracking

---

# If you'd like, I can also generate

1. **the exact FastAPI route definitions**
2. **the prompts.py code structure**
3. **the local watcher architecture**
4. **the DB schema patch**

which would make Claude Code’s job **dramatically easier and safer**.
