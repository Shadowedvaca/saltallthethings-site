# Post-Production Phase 6 — Image Generation & Drive Upload

## Goal

Take the approved image prompt from Phase 5 and generate the album art via DALL-E 3.
Upload the generated image to the Google Drive Cover Art folder. Store the Drive file
ID on the idea record so the website can display it. Update the asset inventory to
reflect the art as present.

---

## Context

Read before starting:
- `reference/postprod-phase-5-art-direction.md` — art direction endpoint, prompt shape
- `reference/postprod-phase-2-gdrive.md` — Drive upload pattern, service account auth
- `CLAUDE.md` — no SDK rule (httpx only), ai_client.py pattern

### Why DALL-E 3

The user already has an OpenAI API key stored in `satt.config`. The existing
`call_openai()` in `ai_client.py` uses it. DALL-E 3 is OpenAI's image model and uses
the same key — no new credentials needed.

DALL-E 3 is the only image generation model supported in this phase. Claude / Anthropic
does not currently offer image generation. If the user later wants Stable Diffusion or
another model, that would be a future addition.

### Image output format

DALL-E 3 returns either:
- A temporary URL (valid for 1 hour), or
- Base64-encoded image data

Request `response_format: "b64_json"` to get base64 — this avoids the URL expiry
problem and lets us upload to Drive immediately.

---

## `src/satt/ai_client.py` Addition

Add `call_dalle()`:

```python
async def call_dalle(prompt: str, config: dict) -> bytes:
    """Call DALL-E 3 image generation. Returns raw PNG bytes."""
```

Uses `config["openaiApiKey"]`. Calls:
```
POST https://api.openai.com/v1/images/generations
```

Request body:
```json
{
  "model": "dall-e-3",
  "prompt": "<the final image prompt>",
  "n": 1,
  "size": "1024x1024",
  "quality": "standard",
  "response_format": "b64_json"
}
```

Decodes the base64 response and returns raw PNG bytes.

Raises `httpx.HTTPStatusError` on API errors (content policy violations, etc.) so the
endpoint can return a useful error message.

---

## `src/satt/gdrive.py` Addition

Add `upload_file_to_folder()`:

```python
async def upload_file_to_folder(
    access_token: str,
    folder_id: str,
    filename: str,
    content: bytes,
    mime_type: str = "image/png"
) -> str:
    """Upload a file to a Drive folder. Returns the new Drive file ID."""
```

Uses the multipart upload endpoint:
```
POST https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart
```

Metadata part:
```json
{
  "name": "EP001_War-Within-Seasons-Ranked_2026-01-20.png",
  "parents": ["<cover_art_folder_id>"]
}
```

Returns the newly created file's Drive ID.

If a file with the same name already exists in the folder (regeneration case), delete
the old file before uploading. This prevents duplicate art files in Drive.

Add `delete_file()`:
```python
async def delete_file(access_token: str, file_id: str) -> None
```
Calls `DELETE https://www.googleapis.com/drive/v3/files/{file_id}`.

---

## `src/satt/routes/ai.py` Addition

### Request model

```python
class GenerateEpisodeArtRequest(BaseModel):
    ideaId: str
    imagePrompt: str  # the finalImagePrompt from Phase 5 (possibly user-edited)
```

### Endpoint

```
POST /api/ai/generate-episode-art
```

Requires JWT auth. Requires OpenAI key in config.

Behavior:
1. Load config — validate `openaiApiKey` present
2. Load the idea and its slot (for `production_file_key` and episode number)
3. If no `production_file_key` on the slot, return 400 (can't name the file)
4. Generate image via `call_dalle(imagePrompt, config)` → PNG bytes
5. Get Drive access token via `get_drive_access_token()`
6. Determine filename: `{production_file_key}.png`
7. Check if art file already exists in Cover Art folder (from asset_inventory):
   - If yes, delete the old Drive file
8. Upload PNG bytes to Cover Art folder via `upload_file_to_folder()`
9. Get returned Drive file ID
10. Save Drive file ID to `Idea.image_file_id`
11. Trigger single-slot Drive scan to refresh `asset_inventory`
12. Return response

### Response

```json
{
  "imageFileId": "1abc...",
  "filename": "EP001_War-Within-Seasons-Ranked_2026-01-20.png"
}
```

---

## Saving `image_file_id` to Idea

The `Idea.image_file_id` column already exists in the schema (Phase 1 found it
pre-existing but unused).

Add a CRUD helper:

```python
async def set_idea_image_file_id(db: AsyncSession, idea_id: str, file_id: str) -> None
```

Updates `Idea.image_file_id` for the given idea.

---

## Displaying Art on the Website

The existing website (`index.html`) already uses Google Drive file IDs to embed images.
The pattern for displaying a Drive image by file ID is:
```
https://drive.google.com/thumbnail?id={file_id}&sz=w1000
```
or
```
https://lh3.googleusercontent.com/d/{file_id}
```

The `GET /public/episodes` endpoint should be updated to include `imageFileId` in its
response so the public-facing episode list can show album art. This is a one-line
addition to the serializer and the query in `crud.get_released_episodes()`.

---

## Post-Production Tab UI Addition (Phase 5 extension)

After the user reviews the art direction panel:
- "Generate Art" button calls `POST /api/ai/generate-episode-art`
- Show a loading state (DALL-E 3 takes 10–30 seconds)
- On success:
  - Show the generated image inline (fetch from Drive thumbnail URL using returned file_id)
  - Asset inventory row for Album Art updates to "ok" (green)
  - "Regenerate" button appears (allows re-running with same or edited prompt)
- On content policy error: show specific toast "OpenAI rejected the prompt — try editing it"
- On other error: generic error toast

The image preview uses:
```
https://drive.google.com/thumbnail?id={imageFileId}&sz=w400
```

---

## Regeneration Flow

When the user clicks "Regenerate":
1. The art direction panel is still visible with the previous prompt
2. User can edit the `finalImagePrompt` text area
3. Click "Generate Art" again
4. Old Drive file is deleted, new one uploaded, `image_file_id` updated

The `artLog` is not appended again on regeneration — the log entry from Phase 5 stands.

---

## Tests

Add to `src/satt/tests/test_ai.py`:
- `POST /api/ai/generate-episode-art` calls DALL-E and returns file ID (mocked)
- 400 returned if no `production_file_key` on slot
- 400 returned if no OpenAI key in config
- `image_file_id` saved on idea after successful generation
- `asset_inventory` updated (via scan mock) after generation

Add to `src/satt/tests/test_gdrive.py`:
- `upload_file_to_folder` sends correct multipart request (mocked)
- `delete_file` sends correct DELETE request (mocked)

---

## Deliverables Checklist

- [ ] `call_dalle()` added to `ai_client.py`, returns PNG bytes
- [ ] `upload_file_to_folder()` added to `gdrive.py`
- [ ] `delete_file()` added to `gdrive.py`
- [ ] `POST /api/ai/generate-episode-art` endpoint implemented
- [ ] Old Drive art file deleted before re-upload (regeneration safe)
- [ ] `image_file_id` saved to `Idea` after upload
- [ ] Single-slot Drive scan triggered after upload
- [ ] `GET /public/episodes` includes `imageFileId` in response
- [ ] "Generate Art" button in UI calls endpoint with (possibly edited) prompt
- [ ] Image preview displayed inline after generation
- [ ] "Regenerate" button works
- [ ] Content policy error shown with specific message
- [ ] Tests pass

---

## Full Post-Production Flow Summary

After all 6 phases, the complete workflow is:

```
1. Recording day arrives (record_date <= today)
   → Episode appears in Post-Production tab

2. User sets production_file_key (e.g. EP042_Topic-Name_2026-03-06)

3. User uploads raw glued WAV to Google Drive → Raw Dog Recordings folder
   → Watcher detects new file → auto-transcribes → notifies server
   → Tab shows: Raw ok, Transcript ok, Art missing, Finished missing
   → nextStep: Generate art

4. User clicks "Generate Art Direction"
   → Transcript fetched from Drive, sent to AI
   → Art direction panel appears with scene concept and prompt

5. User reviews/edits prompt → clicks "Generate Art"
   → DALL-E generates image → uploaded to Cover Art folder in Drive
   → Tab shows: Raw ok, Transcript ok, Art ok, Finished missing
   → nextStep: Awaiting editor

6. If releasing raw: done. If waiting for Skate:
   Skate uploads finished MP3 → Watcher re-transcribes → notifies server
   → Tab shows: Raw ok, Transcript ok (refreshed), Art ok, Finished ok
   → nextStep: Complete
   → User can optionally regenerate art from cleaner transcript
```
