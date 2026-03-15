# Post-Production Phase 2 — Google Drive Asset Inventory

## Goal

Wire the server to Google Drive so it can scan the four asset folders, match files to
episode `production_file_key` values, and store the asset inventory on each ShowSlot.

After this phase, the post-production queue shows real asset status without any local
watcher or file push from the user's machine.

---

## Context

Read before starting:
- `reference/postprod-phase-1-schema.md` — completed prior phase
- `reference/ChatGPT-Answers.md` — folder structure, filename pattern, Drive ID notes
- `CLAUDE.md` — server info, no SDK rule (httpx only), config storage

### Why Google Drive API (not local watcher push)

The user confirmed files live in Google Drive shared folders (not just locally synced).
The user explicitly said: "we should be looking at google drive folders, I can provide
IDs for each folder." Google Drive file IDs are already used in the existing app to
display art on the website.

The server calls the Google Drive API directly — lightweight file listing, no heavy
processing. The 4GB RAM constraint is not a concern for API calls.

The local machine still runs WhisperX (Phase 4). This phase is only about knowing
whether files exist and getting their Drive metadata.

### Filename pattern

The `production_file_key` is the full base name, e.g.:
```
EP001_War-Within-Seasons-Ranked_2026-01-20
```

Asset resolution:
- Raw audio: `EP001_War-Within-Seasons-Ranked_2026-01-20.wav` in Raw Dog Recordings folder
- Finished audio: `EP001_War-Within-Seasons-Ranked_2026-01-20.mp3` in Finished Episodes folder
- Transcript txt: `EP001_War-Within-Seasons-Ranked_2026-01-20.txt` in Transcripts folder
- Transcript json: `EP001_War-Within-Seasons-Ranked_2026-01-20.json` in Transcripts folder
- Album art: `EP001_War-Within-Seasons-Ranked_2026-01-20.png` in Cover Art folder

Matching is by exact filename (key + extension). If multiple files match a key prefix,
that is a conflict state.

---

## Google Drive API Setup

### Authentication

Use a **Google service account** with Drive read access to the shared folder.

The service account JSON key is stored in the `.env` file on the server:
```
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
```

Add to `src/satt/config.py`:
```python
google_service_account_json: str = ""
```

The service account needs to be granted access to the shared Google Drive folder
(either by sharing the folder with the service account email, or via a shared drive
with the account as a member).

### Folder IDs

The four folder IDs are stored in `satt.config` (existing JSONB blob, no migration):
- `gdriveFolderRawAudio`
- `gdriveFolderFinishedAudio`
- `gdriveFolderTranscripts`
- `gdriveFolderCoverArt`

The user enters these in the Config page. They look like: `1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms`

---

## New Module: `src/satt/gdrive.py`

Use raw `httpx` calls to the Google Drive API v3. No Google client libraries (matches
the project's no-SDK rule for external services).

Authentication flow:
1. Parse service account JSON from config
2. Generate a JWT assertion (RS256, signed with the service account private key)
3. Exchange for an access token via `POST https://oauth2.googleapis.com/token`
4. Use the access token as `Authorization: Bearer` on Drive API calls

Note: the standard library `cryptography` or `jwt` package can sign the JWT. Check
whether these are already installed in the venv before adding dependencies.

### Core functions

```python
async def get_drive_access_token(service_account_json: str) -> str
```
Returns a fresh OAuth2 access token for the service account.

```python
async def list_folder_files(access_token: str, folder_id: str) -> list[dict]
```
Calls `GET https://www.googleapis.com/drive/v3/files` with:
- `q: '{folder_id}' in parents and trashed = false`
- `fields: files(id, name, modifiedTime)`

Returns list of `{id, name, modifiedTime}` dicts.

```python
async def build_asset_inventory(slot_id: str, production_file_key: str, config: dict) -> dict
```
Given a key and the four folder IDs from config, scans all four folders and returns
an `asset_inventory` dict matching the schema from Phase 1:

```json
{
  "scanned_at": "...",
  "raw_audio": { "present": true/false, "drive_file_id": "...", "modified": "..." },
  "finished_audio": { "present": true/false, ... },
  "transcript_txt": { "present": true/false, ... },
  "transcript_json": { "present": true/false, ... },
  "album_art": { "present": true/false, ... }
}
```

Conflict detection: if more than one file matches a key+extension pattern, set
`"conflict": true` on that asset entry instead of `present: true`.

---

## New API Route: `POST /api/postproduction/scan`

Add to `src/satt/routes/postproduction.py`.

Requires JWT auth.

Behavior:
1. Load config (get folder IDs and service account JSON)
2. Validate that folder IDs and service account are configured; return 400 if not
3. Load all ShowSlots where `record_date <= today` and `production_file_key IS NOT NULL`
4. For each slot, call `build_asset_inventory()`
5. Write result to `ShowSlot.asset_inventory` via `set_asset_inventory()`
6. Return summary: how many slots were scanned, any errors

This is triggered by the user clicking "Refresh" in the UI (Phase 3). It is also
callable from the local watcher (Phase 4) after transcription completes.

Response:
```json
{
  "scanned": 5,
  "errors": []
}
```

---

## Single-slot scan

Also add to the route:

`POST /api/postproduction/{slot_id}/scan`

Scans a single slot's assets and updates its inventory. Used when the UI needs to
refresh one row without rescanning everything.

---

## Token Caching

Access tokens are valid for 1 hour. Cache the token in-process (a module-level dict
`{expiry: datetime, token: str}`) and refresh only when expired. Do not cache across
restarts — generate fresh on first use after startup.

---

## Config Page Addition (minimal)

Add four text input fields to `config.html` for the Google Drive folder IDs. These
use the existing config save/load pattern already in the frontend. No new backend
routes needed — they flow through the existing `PUT /api/data/config` endpoint.

Also add a "Service Account" section pointing users to set `GOOGLE_SERVICE_ACCOUNT_JSON`
in `.env` on the server (this is sensitive and cannot go in the DB config).

---

## Tests

Add `src/satt/tests/test_gdrive.py` covering:
- `list_folder_files` with a mocked httpx response (use `respx`)
- `build_asset_inventory` correctly marks present/missing/conflict
- `POST /api/postproduction/scan` returns 400 when folder IDs not configured
- `POST /api/postproduction/scan` calls scan for each eligible slot

---

## Deliverables Checklist

- [ ] `GOOGLE_SERVICE_ACCOUNT_JSON` added to `.env` on server and to `config.py` settings
- [ ] `src/satt/gdrive.py` implemented with token fetch, folder listing, inventory builder
- [ ] Conflict detection works (multiple files matching same key)
- [ ] `POST /api/postproduction/scan` (all slots) implemented
- [ ] `POST /api/postproduction/{slot_id}/scan` (single slot) implemented
- [ ] `GET /api/postproduction` (Phase 1) returns fresh data after scan
- [ ] Config page has four folder ID inputs + service account note
- [ ] Tests pass with mocked Drive API responses

---

## What This Phase Does NOT Include

- Post-production UI tab (Phase 3)
- Transcription automation (Phase 4)
- Art direction or image generation (Phases 5-6)
