# Post-Production Phase 1 — Schema, Data Model & Core API

## Goal

Extend the existing database schema and backend to support the post-production workflow.
No UI yet. No Google Drive integration yet. Just the data model, migrations, and the
bare-bones API endpoints the later phases will build on.

This phase is entirely backend — no frontend changes.

---

## Context

Read these before starting:
- `reference/ChatGPT-Answers.md` — authoritative decisions and data model context
- `reference/ChatGPT-reference.md` — AI/art system spec from ChatGPT
- `CLAUDE.md` — repo structure, server info, conventions

The existing app uses:
- `ShowSlot` — episode scheduling (episode_number, record_date, release_date)
- `Idea` — episode content (titles, summary, outline, status, image_file_id)
- `Assignment` — links ShowSlot → Idea

The post-production flow uses `ShowSlot` as its anchor (it owns the dates and episode
number). `Idea` holds content and art references.

---

## What Needs to Be Added

### 1. `ShowSlot.production_file_key` (Alembic migration)

New nullable text column on `satt.show_slots`.

This is the canonical filename base for all asset lookups. Example value:
`EP001_War-Within-Seasons-Ranked_2026-01-20`

All asset types resolve from this key:
- Raw audio: `{key}.wav` in the Raw Dog Recordings folder
- Finished audio: `{key}.mp3` in the Finished Episodes folder
- Transcript txt: `{key}.txt` in the Transcripts folder
- Transcript json: `{key}.json` in the Transcripts folder
- Album art: `{key}.png` in the Cover Art folder

The user sets this manually via the UI (later phase). It can be pre-populated from
`ShowSlot.episode_number` as a convenience default, but is editable.

### 2. `ShowSlot.asset_inventory` (Alembic migration)

New nullable JSONB column on `satt.show_slots`.

Stores the last-known asset presence metadata for this episode, pushed by the
server's Google Drive scan (Phase 2). Example shape:

```json
{
  "scanned_at": "2026-03-01T20:00:00Z",
  "raw_audio": {
    "present": true,
    "drive_file_id": "1abc...",
    "modified": "2026-03-01T18:22:00Z"
  },
  "finished_audio": {
    "present": false
  },
  "transcript_txt": {
    "present": true,
    "drive_file_id": "1def...",
    "modified": "2026-03-01T19:05:00Z"
  },
  "transcript_json": {
    "present": true,
    "drive_file_id": "1ghi...",
    "modified": "2026-03-01T19:05:00Z"
  },
  "album_art": {
    "present": false
  }
}
```

This is written by the scan process (Phase 2) and read by the UI (Phase 3). The
web app never accesses Google Drive files directly from the browser.

### 3. `satt.config` JSONB additions (no migration needed)

Add these keys to the existing `satt.config` JSONB blob. They are editable via the
Config page (future) and consumed by the art generation phases (Phases 5-6):

- `artStyleBible` — object: brand character rules, style rules, lighting rules, palette
- `artArchetypes` — array: the 6 scene archetypes (Tavern, Delve, Raid, Workshop, Lore, Auction)
- `artLog` — array: continuity log entries (grows over time, read in Phase 5)
- `gdriveFolderRawAudio` — string: Google Drive folder ID for Raw Dog Recordings
- `gdriveFolderFinishedAudio` — string: Google Drive folder ID for Finished Episodes
- `gdriveFolderTranscripts` — string: Google Drive folder ID for Transcripts
- `gdriveFolderCoverArt` — string: Google Drive folder ID for Cover Art

These folder IDs are entered by the user in the Config page. They do not need a schema
migration — the existing `satt.config.data` JSONB accommodates them.

---

## Alembic Migration

One migration covering both new columns:

```
PYTHONPATH=src alembic revision --autogenerate -m "add production_file_key and asset_inventory to show_slots"
```

Review and apply:
```
PYTHONPATH=src alembic upgrade head
```

---

## New CRUD Helpers (`src/satt/crud.py`)

Add:

```python
async def get_postproduction_queue(db: AsyncSession) -> list[dict]
```
Returns all ShowSlots where `record_date <= today`, joined to their Idea (if assigned),
ordered by `record_date DESC`. Each row includes:
- slot fields: id, episode_number, episode_num, record_date, release_date, production_file_key, asset_inventory
- idea fields (if assigned): id, selected_title, summary, status, image_file_id

```python
async def set_production_file_key(db: AsyncSession, slot_id: str, key: str) -> None
```
Updates `ShowSlot.production_file_key` for the given slot.

```python
async def set_asset_inventory(db: AsyncSession, slot_id: str, inventory: dict) -> None
```
Updates `ShowSlot.asset_inventory` for the given slot.

---

## New API Routes (`src/satt/routes/postproduction.py`)

Create a new route file. Register it in `main.py`.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/postproduction` | Return the full post-production queue |
| `PUT` | `/api/postproduction/{slot_id}/key` | Set production_file_key for a slot |

Both require JWT auth (`require_auth`).

### `GET /api/postproduction`

Returns array of episode rows. Each row:

```json
{
  "slotId": "...",
  "episodeNumber": "EP001",
  "episodeNum": 1,
  "recordDate": "2026-01-20",
  "releaseDate": "2026-01-22",
  "productionFileKey": "EP001_War-Within-Seasons-Ranked_2026-01-20",
  "ideaId": "...",
  "selectedTitle": "War Within Seasons Ranked",
  "ideaStatus": "draft",
  "imageFileId": null,
  "assetInventory": { ... },
  "nextStep": "transcript"
}
```

The `nextStep` field is computed server-side from `asset_inventory` using this logic:

```
if production_file_key is null         → "set_key"
if raw_audio.present is false          → "upload_raw"
if transcript_txt.present is false     → "transcribe"
if transcript stale (audio.modified > transcript.modified) → "retranscribe"
if album_art.present is false          → "generate_art"
if finished_audio.present is false     → "awaiting_editor"
else                                   → "complete"
```

### `PUT /api/postproduction/{slot_id}/key`

Request body:
```json
{ "productionFileKey": "EP001_War-Within-Seasons-Ranked_2026-01-20" }
```

Updates the key, returns the updated slot row.

---

## Serializer (`src/satt/serializers.py`)

Add `serialize_postprod_row(slot, idea)` that produces the camelCase output shape above.

---

## Tests

Add `src/satt/tests/test_postproduction.py` covering:
- `GET /api/postproduction` returns only slots where record_date <= today
- `GET /api/postproduction` returns slots sorted desc by record_date
- `PUT /api/postproduction/{slot_id}/key` updates the key
- `nextStep` computed correctly for each state

---

## Deliverables Checklist

- [ ] Alembic migration written and reviewed
- [ ] `production_file_key` and `asset_inventory` columns exist in `satt.show_slots`
- [ ] `get_postproduction_queue()` CRUD helper implemented
- [ ] `set_production_file_key()` CRUD helper implemented
- [ ] `set_asset_inventory()` CRUD helper implemented
- [ ] `GET /api/postproduction` returns correct queue with nextStep
- [ ] `PUT /api/postproduction/{slot_id}/key` works
- [ ] Router registered in `main.py`
- [ ] Serializer handles null asset_inventory gracefully
- [ ] Tests pass

---

## What This Phase Does NOT Include

- Google Drive API integration (Phase 2)
- Post-production UI tab (Phase 3)
- Transcription automation (Phase 4)
- Art direction or image generation (Phases 5-6)
