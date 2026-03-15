# Post-Production Phase 4 — Local Transcription Watcher

## Goal

Automate transcription on the recording PC. When a new raw recording lands in Google
Drive, transcription starts automatically. When Skate's finished file arrives, it
re-transcribes and replaces the old transcript. After transcription, the watcher
notifies the server to refresh the asset inventory for that episode.

All of this runs on the local machine. The server is not involved in transcription.

---

## Context

Read before starting:
- `reference/postprod-phase-1-schema.md` — production_file_key, asset model
- `reference/postprod-phase-2-gdrive.md` — scan endpoint the watcher calls after transcription
- `CLAUDE.md` — local scripts are in `scripts/`, WhisperX runs locally

Existing scripts to extend:
- `scripts/transcribe.bat` — current manual transcription runner (keep as-is)
- `scripts/label-speakers.py` — speaker identification (needs `--auto` flag added)
- `scripts/secrets.bat` — HF_TOKEN for diarization

The existing `transcribe.bat` stays unchanged — it is still the manual tool for when
you want interactive control. The new scripts are additive.

---

## File Storage Reality

Google Drive is the source of truth for all files. The recording machine has Google
Drive for Desktop installed, which mounts the shared folder at:
```
J:\Shared drives\Salt All The Things\Show Recordings\
```

The watcher watches these locally synced paths. When Drive syncs a new file down from
another machine (e.g., Skate uploads the finished episode), the local sync triggers
a file system event which the watcher catches.

Transcription output (`.txt` and `.json` files) is written back to the Transcripts
folder in the local sync path, and Google Drive automatically syncs it up to the cloud.

---

## Change 1: Add `--auto` Flag to `label-speakers.py`

### Problem

`label-speakers.py` blocks waiting for interactive input — you type which speaker is
which. This makes automation impossible.

### Solution

Add `--auto` flag. When set, it skips the prompts and assigns speakers in order of
first appearance:
- SPEAKER_00 → first host in `--hosts` list (default: Rocket)
- SPEAKER_01 → second host in `--hosts` list (default: Trog)
- SPEAKER_02+ → "Guest" or "Unknown"

WhisperX assigns speaker IDs in order of first appearance in the audio, so SPEAKER_00
is whoever speaks first. For a two-host show this is usually consistent. If it flips
on a given episode, the user can re-run the manual `transcribe.bat` to fix it.

### Implementation

In `label-speakers.py`, add to argparse:
```python
parser.add_argument("--auto", action="store_true",
    help="Skip interactive prompts; assign speakers in appearance order")
```

In `main()`, if `args.auto` is True, build the mapping directly:
```python
mapping = {
    speaker_ids[i]: (args.hosts[i] if i < len(args.hosts) else "Unknown")
    for i in range(len(speaker_ids))
}
```
Print the auto-assignment to stdout so it's visible in logs, then proceed to
`build_transcript()` and write output as normal.

---

## New Script: `scripts/transcribe-auto.py`

Non-interactive transcription for a single file. Takes the audio file path as an
argument. Called by the watcher.

```
python scripts/transcribe-auto.py <audio_file_path> [--notify-server]
```

Behavior:
1. Validate the file exists and is `.wav` or `.mp3`
2. Determine output paths (Transcripts folder, same base name, `.json` and `.txt`)
3. Run WhisperX with diarization:
   ```
   whisperx <file> --model medium --language en --compute_type int8
             --diarize --hf_token <HF_TOKEN> --output_format json
             --output_dir <TRANSCRIPTS_DIR>
   ```
4. If WhisperX succeeds and JSON exists, run `label-speakers.py` with `--auto`:
   ```
   python scripts/label-speakers.py <json_out> <txt_out> --hosts Rocket Trog --auto
   ```
5. Print completion status
6. If `--notify-server` flag is set, call the server scan endpoint (see below)

Load `HF_TOKEN` and folder paths from `scripts/secrets.bat` or a parallel
`scripts/secrets.py` (the bat file isn't importable from Python — create
`secrets.py` or read from environment variable `HF_TOKEN`).

### Folder paths (in the script)

```python
SHARED_ROOT = r"J:\Shared drives\Salt All The Things\Show Recordings"
RAW_DIR = SHARED_ROOT + r"\Raw Dog Recordings"
FINISHED_DIR = SHARED_ROOT + r"\Finished Episodes"
TRANSCRIPTS_DIR = SHARED_ROOT + r"\Transcripts"
```

These should be configurable at the top of the file (same as `transcribe.bat`).

---

## New Script: `scripts/watch.py`

Folder watcher. Runs as a background process on the recording machine. Uses Python's
`watchdog` library (install: `pip install watchdog`).

### Watches two folders

1. `Raw Dog Recordings\` — for new WAV files (raw glued recording)
2. `Finished Episodes\` — for new MP3 files (Skate's edit)

### On new file in Raw Dog Recordings

- Wait 30 seconds (allow large file to finish syncing/copying before starting)
- Call `transcribe-auto.py <file> --notify-server`

### On new file in Finished Episodes

- Wait 30 seconds
- Find the matching transcript in the Transcripts folder (same base name)
- If transcript exists: log "Replacing transcript for {name}"
- Call `transcribe-auto.py <file> --notify-server` (overwrites existing transcript)

### Staleness note

The `--notify-server` flag triggers a single-slot Drive scan after transcription,
which updates the `asset_inventory` on that episode. This is how the web UI gets
updated — the watcher calls the server, the server rescans Drive, the browser sees
fresh data on next load or refresh.

### Server notification

After transcription, the watcher calls:
```
POST https://saltallthethings.com/api/postproduction/scan
Authorization: Bearer <jwt_token>
```

The JWT token is stored in `scripts/secrets.py` (or `secrets.bat`) as `SATT_API_TOKEN`.
The user generates a long-lived token by logging in and copying it from the browser.
(A dedicated service account token endpoint could be added later if needed.)

### Running the watcher

```
python scripts/watch.py
```

Can be added to Windows startup (Task Scheduler, startup folder, or a `.bat` wrapper)
so it runs automatically when the machine boots.

---

## `scripts/secrets.py` (new, git-ignored)

Python equivalent of `secrets.bat`, importable by `transcribe-auto.py` and `watch.py`:

```python
HF_TOKEN = "your_huggingface_token_here"
SATT_API_TOKEN = "your_jwt_token_here"
```

Add `scripts/secrets.py` to `.gitignore` alongside `scripts/secrets.bat`.

Add `scripts/secrets.py.example`:
```python
HF_TOKEN = "your_huggingface_token_here"
SATT_API_TOKEN = "your_jwt_token_here"  # JWT from saltallthethings.com login
```

---

## Handling the "Release Raw" Case

The user noted: "if Skate is not able to finish the episode in time, we are releasing
these as raw."

The watcher does not need special handling for this — it transcribes the raw recording
regardless. The web UI (Phase 3) shows `finished_audio: missing` in that case, and
`nextStep` shows "Awaiting editor" once all other assets are present. The user can
choose to publish with raw audio at any time; the app tracks it as a separate asset.

---

## Deliverables Checklist

- [ ] `label-speakers.py` has `--auto` flag that skips prompts and assigns in order
- [ ] Auto-assignment is logged to stdout (visible in watcher output)
- [ ] `scripts/transcribe-auto.py` runs end-to-end for a WAV or MP3 file
- [ ] `transcribe-auto.py` calls `label-speakers.py --auto` after WhisperX
- [ ] `transcribe-auto.py --notify-server` calls the server scan endpoint
- [ ] `scripts/watch.py` watches both folders
- [ ] Watcher fires on new `.wav` in Raw Dog Recordings
- [ ] Watcher fires on new `.mp3` in Finished Episodes
- [ ] 30-second delay before starting transcription (sync settle)
- [ ] `scripts/secrets.py` and `secrets.py.example` created
- [ ] `scripts/secrets.py` added to `.gitignore`
- [ ] Existing `transcribe.bat` unchanged
- [ ] `watchdog` added to install notes or a `scripts/requirements.txt`

---

## What This Phase Does NOT Include

- Art direction or image generation (Phases 5-6)
- Any UI changes
- Any server-side changes beyond using the existing Phase 2 scan endpoint
