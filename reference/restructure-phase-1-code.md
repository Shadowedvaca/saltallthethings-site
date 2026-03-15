# Drive Restructure — Phase 1: Code Changes

All changes are in this repo. Deploy to the server before running the Drive
migration. Scanning will be broken between deploy and migration — that is expected.

---

## 1. `src/satt/gdrive.py`

This is the largest change. The scan logic needs to:
1. Find the episode subfolder inside the root folder (by name = key).
2. List all files in that subfolder.
3. Match each asset type by prefix + extension.

### 1a. New helper: `find_episode_folder`

Add a function that searches the root `Show Recordings` folder for a subfolder
whose name exactly matches `production_file_key`. Drive folders are files with
`mimeType = application/vnd.google-apps.folder`.

```python
async def find_episode_folder(
    access_token: str, root_folder_id: str, key: str
) -> str | None:
    """Search root_folder_id for a subfolder named exactly `key`.
    Returns the folder ID string, or None if not found.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            _DRIVE_FILES_URL,
            params={
                "q": (
                    f"'{root_folder_id}' in parents"
                    " and mimeType = 'application/vnd.google-apps.folder'"
                    f" and name = '{key}'"
                    " and trashed = false"
                ),
                "fields": "files(id,name)",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        files = resp.json().get("files", [])
    return files[0]["id"] if files else None
```

**Note:** If the key contains special characters that need escaping in Drive
query syntax (apostrophes, etc.), add escaping. The current key format
(`EP001_Title-Words_YYYY-MM-DD`) only contains alphanumeric, hyphens, and
underscores, so no escaping is needed.

### 1b. Update `_match_files` → add `_prefix_match`

The old `_match_files` did an exact name match (`{key}.{ext}`). The new
convention uses prefixes. Add a prefix-matching variant:

```python
def _prefix_match(files: list[dict], prefix: str, ext: str) -> list[dict]:
    """Return files whose name starts with `prefix` and ends with `.{ext}` (case-insensitive)."""
    suffix = f".{ext}".lower()
    pfx = prefix.lower()
    return [f for f in files if f["name"].lower().startswith(pfx) and f["name"].lower().endswith(suffix)]
```

Keep `_match_files` for the finished episode (which has no prefix — exact match
on `{key}.mp3`).

### 1c. Rewrite `build_asset_inventory`

Replace the current implementation that scans 4 separate folders. The new
version:
1. Gets an access token.
2. Calls `find_episode_folder` with `config["gdriveFolderShowRecordings"]`.
3. If no folder found, returns an inventory where everything is `{"present": False}`.
4. Lists all files in the episode folder.
5. Matches each asset by prefix/ext.

```python
async def build_asset_inventory(
    slot_id: str, production_file_key: str, config: dict
) -> dict:
    """Scan the episode subfolder in Drive and return an asset_inventory dict.

    config must contain:
      - clientId, clientSecret, refreshToken (OAuth2 credentials)
      - gdriveFolderShowRecordings: root Show Recordings folder ID
    """
    access_token = await get_drive_access_token(
        config["clientId"], config["clientSecret"], config["refreshToken"]
    )

    root_folder_id = config["gdriveFolderShowRecordings"]
    key = production_file_key

    episode_folder_id = await find_episode_folder(access_token, root_folder_id, key)

    if not episode_folder_id:
        absent = {"present": False}
        return {
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "episode_folder_id": None,
            "raw_audio": absent,
            "raw_trog": absent,
            "raw_rocket": absent,
            "finished_audio": absent,
            "transcript_txt": absent,
            "transcript_json": absent,
            "album_art": absent,
            "art_direction": absent,
        }

    files = await list_folder_files(access_token, episode_folder_id)

    return {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "episode_folder_id": episode_folder_id,
        "raw_audio":      _asset_entry(_prefix_match(files, f"Raw_Dog_{key}", "wav")),
        "raw_trog":       _asset_entry(_prefix_match(files, f"Trog_{key}", "wav")),
        "raw_rocket":     _asset_entry(_prefix_match(files, f"Rocket_{key}", "wav")),
        "finished_audio": _asset_entry(_match_files(files, key, "mp3")),
        "transcript_txt": _asset_entry(_prefix_match(files, f"Transcript_{key}", "txt")),
        "transcript_json":_asset_entry(_prefix_match(files, f"Transcript_{key}", "json")),
        "album_art":      _asset_entry(_prefix_match(files, f"Cover_Art_{key}", "png")),
        "art_direction":  _asset_entry(_prefix_match(files, f"Art_Direction_{key}", "json")),
    }
```

**Note:** `episode_folder_id` is stored in the inventory so that `ai.py` can
use it for uploads without a second folder-lookup. See section 3 below.

---

## 2. `src/satt/routes/postproduction.py`

### 2a. `_check_scan_config` — replace 4-folder check

Old:
```python
if not db_config.get("gdriveFolderRawAudio"):
    missing.append("gdriveFolderRawAudio")
if not db_config.get("gdriveFolderFinishedAudio"):
    missing.append("gdriveFolderFinishedAudio")
if not db_config.get("gdriveFolderTranscripts"):
    missing.append("gdriveFolderTranscripts")
if not db_config.get("gdriveFolderCoverArt"):
    missing.append("gdriveFolderCoverArt")
```

New:
```python
if not db_config.get("gdriveFolderShowRecordings"):
    missing.append("gdriveFolderShowRecordings")
```

No other changes to this file.

---

## 3. `src/satt/routes/ai.py`

### 3a. Art direction upload (`generate_art_direction`)

Currently uploads to `gdriveFolderCoverArt` as `{key}_artdirection.json`.

New behaviour:
1. Read `episode_folder_id` from the slot's existing `asset_inventory` (set
   during the last scan). If present, upload there directly.
2. If `episode_folder_id` is not in the inventory (slot was never scanned, or
   inventory is stale), call `find_episode_folder` to get it.
3. Upload as `Art_Direction_{key}.json`.

Find the block that currently does:
```python
cover_art_folder_id = config.get("gdriveFolderCoverArt")
if cover_art_folder_id and slot and slot.production_file_key:
    art_json_filename = f"{slot.production_file_key}_artdirection.json"
```

Replace with:
```python
# Resolve episode folder ID for upload
episode_folder_id = None
if slot and slot.production_file_key:
    # Try inventory first (avoids a second Drive API call)
    inv = slot.asset_inventory or {}
    episode_folder_id = inv.get("episode_folder_id")
    if not episode_folder_id:
        root_folder_id = config.get("gdriveFolderShowRecordings")
        if root_folder_id:
            from satt.gdrive import find_episode_folder
            episode_folder_id = await find_episode_folder(
                access_token, root_folder_id, slot.production_file_key
            )

if episode_folder_id and slot and slot.production_file_key:
    art_json_filename = f"Art_Direction_{slot.production_file_key}.json"
```

Update the `upload_file_to_folder` call to use `episode_folder_id` instead of
`cover_art_folder_id`.

Also update the delete-old-art-direction block: the old art direction ID is
`inv.get("art_direction", {}).get("drive_file_id")` — that logic is unchanged,
only the upload destination and filename change.

### 3b. Episode art upload (`generate_episode_art`)

Currently reads `cover_art_folder_id = config.get("gdriveFolderCoverArt")` and
uploads as `{key}.png`.

New behaviour:
1. Resolve `episode_folder_id` from inventory or via `find_episode_folder` (same
   pattern as 3a above).
2. Upload as `Cover_Art_{key}.png`.

Find the block:
```python
cover_art_folder_id = config.get("gdriveFolderCoverArt")
if not cover_art_folder_id:
    return JSONResponse(status_code=400, ...)
```

Replace folder resolution with the episode folder approach. The error message
should change to mention `gdriveFolderShowRecordings`.

The filename variable `filename` is already constructed as `f"{key}.png"` — change
it to `f"Cover_Art_{key}.png"`.

**Also update the delete-old-art block:** it currently searches for `f"{key}.png"`.
Change to `f"Cover_Art_{key}.png"` (or use the file ID stored in the inventory).

---

## 4. `config.html`

### 4a. Replace the 4 Drive folder inputs with 1

In the Google Drive section (around line 117–133), replace:

```html
<div class="form-group">
  <label>Raw Audio Folder ID <span class="label-hint">— .wav recordings</span></label>
  <input type="text" id="gdriveFolderRawAudio" ...>
</div>
<div class="form-group">
  <label>Finished Audio Folder ID <span class="label-hint">— .mp3 edited episodes</span></label>
  <input type="text" id="gdriveFolderFinishedAudio" ...>
</div>
<div class="form-group">
  <label>Transcripts Folder ID <span class="label-hint">— .txt and .json transcript files</span></label>
  <input type="text" id="gdriveFolderTranscripts" ...>
</div>
<div class="form-group">
  <label>Cover Art Folder ID <span class="label-hint">— .png album art</span></label>
  <input type="text" id="gdriveFolderCoverArt" ...>
</div>
```

With:

```html
<div class="form-group">
  <label>Show Recordings Folder ID <span class="label-hint">— root folder containing episode subfolders</span></label>
  <input type="text" id="gdriveFolderShowRecordings" placeholder="e.g., 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms">
</div>
```

### 4b. Update the JS read block (around line 287–290)

Remove the 4 old lines and add:
```js
document.getElementById('gdriveFolderShowRecordings').value = config.gdriveFolderShowRecordings || '';
```

### 4c. Update the JS write block (around line 321–324)

Remove the 4 old lines and add:
```js
gdriveFolderShowRecordings: document.getElementById('gdriveFolderShowRecordings').value,
```

---

## 5. `js/postproduction.js`

### 5a. Add Trog and Rocket badges (optional but recommended)

The `renderTable()` method currently renders 5 asset badge columns:
Raw, Transcript, Art Dir, Art, Finished.

Add Trog and Rocket columns after Raw:

In the badges block:
```js
const trogBadge    = this._badgeHtml(inv ? inv.raw_trog   : null, hasKey);
const rocketBadge  = this._badgeHtml(inv ? inv.raw_rocket : null, hasKey);
```

Add them to the row HTML and update `colspan` in any `<td colspan="11">` to
`colspan="13"`. Also update `postproduction.html` table `<th>` headers
accordingly. Columns become:

EP | Title | Date | Key | Raw | Trog | Rocket | Transcript | Dir | Art | Finished | Next | Actions

---

## 6. `postproduction.html`

If adding Trog/Rocket columns from step 5, update the `<thead>` row to add:
```html
<th>Trog</th>
<th>Rocket</th>
```
after the Raw column header. Update any `colspan` values in the file.

---

## 7. `scripts/watch.py`

The watcher currently monitors two flat folders. With episode subfolders, it
needs to watch recursively from the shared root.

### 7a. Change the watched directory and approach

Remove `RAW_DIR`, `FINISHED_DIR`, `TRANSCRIPTS_DIR` constants (or update them).

New approach: watch `SHARED_ROOT` recursively. Trigger on:
- Any new `.wav` file whose name starts with `Raw_Dog_` → transcribe it
- Any new `.mp3` file → transcribe it

```python
SHARED_ROOT = r"J:\Shared drives\Salt All The Things\Show Recordings"
SYNC_SETTLE_SECONDS = 30
```

New handler class:

```python
class ShowRecordingsHandler(FileSystemEventHandler):
    """Watches the Show Recordings root recursively for audio files to transcribe."""

    def on_created(self, event):
        if event.is_directory:
            return
        path = event.src_path
        name = os.path.basename(path)
        name_lower = name.lower()
        if name_lower.endswith(".wav") and name_lower.startswith("raw_dog_"):
            print(f"[watch] New raw recording detected: {name}")
            schedule_transcription(path)
        elif name_lower.endswith(".mp3"):
            print(f"[watch] New finished episode detected: {name}")
            schedule_transcription(path)
```

In `main()`, replace the two `observer.schedule` calls with one recursive watch:

```python
observer.schedule(ShowRecordingsHandler(), SHARED_ROOT, recursive=True)
```

Update the startup log messages accordingly.

---

## 8. `scripts/transcribe-auto.py`

Currently writes transcripts to `TRANSCRIPTS_DIR`. New behaviour: write to the
**same folder as the input audio file**, prefixed with `Transcript_`.

### 8a. Key extraction

The audio file name encodes the key:
- `Raw_Dog_{key}.wav` → strip `Raw_Dog_` prefix and `.wav` extension
- `{key}.mp3` → strip `.mp3` extension (finished episode, no prefix)

```python
def _extract_key(audio_path: str) -> str:
    """Extract the production key from an audio filename."""
    name = os.path.splitext(os.path.basename(audio_path))[0]
    if name.lower().startswith("raw_dog_"):
        return name[len("Raw_Dog_"):]   # strip prefix (case-preserved from file)
    return name
```

**Note:** The prefix strip must be case-insensitive in the check but preserve
the rest of the key as-is. The implementation above assumes the prefix is
exactly `Raw_Dog_` (capitalised). Adjust if the actual files use different
casing.

### 8b. Update output paths

Replace:
```python
TRANSCRIPTS_DIR = SHARED_ROOT + r"\Transcripts"
...
basename = os.path.splitext(os.path.basename(audio_path))[0]
json_out = os.path.join(TRANSCRIPTS_DIR, basename + ".json")
txt_out  = os.path.join(TRANSCRIPTS_DIR, basename + ".txt")
```

With:
```python
output_dir = os.path.dirname(audio_path)   # same folder as audio file
key = _extract_key(audio_path)
json_out = os.path.join(output_dir, f"Transcript_{key}.json")
txt_out  = os.path.join(output_dir, f"Transcript_{key}.txt")
```

Also update the `WhisperX` invocation: WhisperX outputs to `--output_dir` with
the audio file's basename. Since WhisperX names its JSON output after the input
file (e.g., `Raw_Dog_EP001_....json`), we need to rename it after WhisperX
completes — OR point WhisperX output to a temp location and rename.

Simplest approach:
1. Pass `--output_dir` as a temp subfolder inside the episode folder.
2. WhisperX outputs `Raw_Dog_{key}.json`.
3. After WhisperX finishes, rename to `Transcript_{key}.json`.
4. Run `label-speakers.py` on the renamed JSON to produce `Transcript_{key}.txt`.

```python
import tempfile, shutil

def transcribe(audio_path: str, hf_token: str, output_dir: str, key: str) -> bool:
    """Run WhisperX; rename output to Transcript_{key}.json in output_dir."""
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            "whisperx", audio_path,
            "--model", WHISPERX_MODEL,
            "--language", "en",
            "--compute_type", "int8",
            "--diarize",
            "--hf_token", hf_token,
            "--output_format", "json",
            "--output_dir", tmp,
        ]
        result = subprocess.run(cmd)
        if result.returncode != 0:
            return False

        # WhisperX names the JSON after the input filename (without extension)
        whisperx_name = os.path.splitext(os.path.basename(audio_path))[0] + ".json"
        whisperx_out  = os.path.join(tmp, whisperx_name)
        target_json   = os.path.join(output_dir, f"Transcript_{key}.json")

        if not os.path.isfile(whisperx_out):
            print(f"[transcribe-auto] ERROR: WhisperX JSON not found: {whisperx_out}")
            return False

        shutil.move(whisperx_out, target_json)
    return True
```

Update `main()` to:
1. Call `_extract_key(audio_path)` to get `key`.
2. Set `output_dir = os.path.dirname(audio_path)`.
3. Call updated `transcribe(audio_path, hf_token, output_dir, key)`.
4. Set `json_out = os.path.join(output_dir, f"Transcript_{key}.json")`.
5. Set `txt_out  = os.path.join(output_dir, f"Transcript_{key}.txt")`.
6. Remove or stop referencing `TRANSCRIPTS_DIR`.

---

## 9. `src/satt/serializers.py`

### 9a. `_compute_next_step` — no logic change needed

The function already reads `inv.get("raw_audio", {})` — this still maps to the
`Raw_Dog_` file. No changes required unless you want to add Trog/Rocket to the
step logic (not recommended).

### 9b. No other serializer changes needed.

---

## Deployment Checklist

After all changes are made locally:

1. Commit and push to `main` (GitHub Actions deploys static files).
2. SSH to server:
   ```bash
   cd /opt/satt-platform && git pull
   sudo systemctl restart satt
   journalctl -u satt -f   # confirm clean startup
   ```
3. No Alembic migration is needed — no schema changes.
4. Verify the Config page loads and shows the new single folder input.

Scanning will fail with "No episode folder found" until Drive migration (Phase 2)
is complete. That is expected.
