# Drive Restructure — Phase 2: File Migration

Run this phase **after** Phase 1 code is deployed and confirmed running on the server.

---

## Overview

You need to:
1. Create one subfolder per episode in `Show Recordings`.
2. Move and rename all existing files into those subfolders.
3. Update the DB config to use the new `gdriveFolderShowRecordings` key.

This can be done in two ways:
- **Option A (recommended): Migration script** — automated Python script using
  the local Drive mount at `J:\Shared drives\Salt All The Things\Show Recordings`.
- **Option B: Manual** — do it by hand in Drive for Explorer.

---

## Option A: Migration Script

Save this as `scripts/migrate-drive-structure.py` and run it on the recording
PC (or any machine with the Drive folder mounted at `J:\`).

```python
"""
migrate-drive-structure.py

Reorganises the Show Recordings folder from flat type-subfolders to per-episode
subfolders. Runs locally against the Google Drive for Desktop mount.

Usage (dry run first!):
    python scripts/migrate-drive-structure.py --dry-run
    python scripts/migrate-drive-structure.py
"""

import argparse
import os
import shutil

SHARED_ROOT = r"J:\Shared drives\Salt All The Things\Show Recordings"

# Source folders (old structure)
SRC_RAW      = os.path.join(SHARED_ROOT, "Raw Dog Recordings")
SRC_FINISHED = os.path.join(SHARED_ROOT, "Finished Episodes")
SRC_TRANSCRIPTS = os.path.join(SHARED_ROOT, "Transcripts")
SRC_COVER_ART   = os.path.join(SHARED_ROOT, "Cover Art")


def _extract_key_from_raw(name: str) -> str | None:
    """EP001_Title_Date.wav → EP001_Title_Date. Returns None if not a WAV."""
    if not name.lower().endswith(".wav"):
        return None
    return os.path.splitext(name)[0]


def _extract_key_from_finished(name: str) -> str | None:
    """EP001_Title_Date.mp3 → EP001_Title_Date. Returns None if not an MP3."""
    if not name.lower().endswith(".mp3"):
        return None
    return os.path.splitext(name)[0]


def _extract_key_from_transcript(name: str) -> str | None:
    """EP001_Title_Date.txt or .json → EP001_Title_Date."""
    base, ext = os.path.splitext(name)
    if ext.lower() not in (".txt", ".json"):
        return None
    return base


def _extract_key_from_art(name: str) -> tuple[str | None, str]:
    """
    EP001_Title_Date.png          → (key, 'cover_art')
    EP001_Title_Date_artdirection.json → (key, 'art_direction')
    Returns (None, '') if unrecognised.
    """
    if name.lower().endswith("_artdirection.json"):
        key = name[:-len("_artdirection.json")]
        return key, "art_direction"
    if name.lower().endswith(".png"):
        return os.path.splitext(name)[0], "cover_art"
    return None, ""


def move_file(src: str, dst: str, dry_run: bool) -> None:
    if dry_run:
        print(f"  [DRY RUN] {src}\n           → {dst}")
    else:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        print(f"  MOVED: {os.path.basename(src)} → {os.path.basename(dst)}")


def migrate(dry_run: bool) -> None:
    print(f"=== Drive Migration {'(DRY RUN) ' if dry_run else ''}===\n")

    # ── Raw Dog Recordings ──────────────────────────────────────────────────
    print("Processing Raw Dog Recordings...")
    for name in sorted(os.listdir(SRC_RAW)):
        src = os.path.join(SRC_RAW, name)
        if os.path.isdir(src):
            continue
        key = _extract_key_from_raw(name)
        if not key:
            print(f"  SKIP (unrecognised): {name}")
            continue
        dst_dir = os.path.join(SHARED_ROOT, key)
        dst = os.path.join(dst_dir, f"Raw_Dog_{key}.wav")
        move_file(src, dst, dry_run)

    # ── Finished Episodes ───────────────────────────────────────────────────
    print("\nProcessing Finished Episodes...")
    for name in sorted(os.listdir(SRC_FINISHED)):
        src = os.path.join(SRC_FINISHED, name)
        if os.path.isdir(src):
            continue
        key = _extract_key_from_finished(name)
        if not key:
            print(f"  SKIP (unrecognised): {name}")
            continue
        dst_dir = os.path.join(SHARED_ROOT, key)
        dst = os.path.join(dst_dir, f"{key}.mp3")  # no prefix
        move_file(src, dst, dry_run)

    # ── Transcripts ─────────────────────────────────────────────────────────
    print("\nProcessing Transcripts...")
    for name in sorted(os.listdir(SRC_TRANSCRIPTS)):
        src = os.path.join(SRC_TRANSCRIPTS, name)
        if os.path.isdir(src):
            continue
        key = _extract_key_from_transcript(name)
        if not key:
            print(f"  SKIP (unrecognised): {name}")
            continue
        _, ext = os.path.splitext(name)
        dst_dir = os.path.join(SHARED_ROOT, key)
        dst = os.path.join(dst_dir, f"Transcript_{key}{ext}")
        move_file(src, dst, dry_run)

    # ── Cover Art ───────────────────────────────────────────────────────────
    print("\nProcessing Cover Art...")
    for name in sorted(os.listdir(SRC_COVER_ART)):
        src = os.path.join(SRC_COVER_ART, name)
        if os.path.isdir(src):
            continue
        key, kind = _extract_key_from_art(name)
        if not key:
            print(f"  SKIP (unrecognised): {name}")
            continue
        dst_dir = os.path.join(SHARED_ROOT, key)
        if kind == "cover_art":
            dst = os.path.join(dst_dir, f"Cover_Art_{key}.png")
        else:
            dst = os.path.join(dst_dir, f"Art_Direction_{key}.json")
        move_file(src, dst, dry_run)

    print("\nDone.")
    if dry_run:
        print("Re-run without --dry-run to actually move files.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be moved without moving anything")
    args = parser.parse_args()
    migrate(args.dry_run)
```

### Running the script

```
# 1. Review first with dry run
python scripts/migrate-drive-structure.py --dry-run

# 2. If output looks correct, run for real
python scripts/migrate-drive-structure.py
```

Wait for Google Drive for Desktop to sync all moves. This may take several
minutes for large audio files. Watch the Drive sync icon in the system tray.

---

## Option B: Manual

For each episode (e.g., EP001):
1. Create folder `EP001_War-Within-Seasons-Ranked_2026-01-20` inside `Show Recordings`.
2. Move each file and rename per the naming convention:

| Source location | Old filename | New filename |
|---|---|---|
| `Raw Dog Recordings/` | `EP001_....wav` | `Raw_Dog_EP001_....wav` |
| `Finished Episodes/` | `EP001_....mp3` | `EP001_....mp3` *(no change)* |
| `Transcripts/` | `EP001_....txt` | `Transcript_EP001_....txt` |
| `Transcripts/` | `EP001_....json` | `Transcript_EP001_....json` |
| `Cover Art/` | `EP001_....png` | `Cover_Art_EP001_....png` |
| `Cover Art/` | `EP001_..._artdirection.json` | `Art_Direction_EP001_....json` |

---

## After Migration: Handle Trog and Rocket Tracks

If individual Trog and Rocket `.wav` tracks exist somewhere, move them into
each episode folder and rename:
- Trog track → `Trog_{key}.wav`
- Rocket track → `Rocket_{key}.wav`

If they don't exist yet, no action needed — the scanner will simply show
those badges as `--` (missing).

---

## Update DB Config

After files are moved (and Drive sync is confirmed), update the config in Postgres.

### Via Config page (easiest)

1. Go to `https://saltallthethings.com/config.html` and log in.
2. In the Google Drive section, enter the Drive folder ID for `Show Recordings`.
   - The folder ID is the long string after `folders/` in its Drive URL.
3. Click Save. The old folder IDs will be dropped automatically because the
   write block no longer includes them.

### Via SQL (if config page is unavailable)

```sql
-- Run on the server:
UPDATE satt.config
SET data = jsonb_set(
    data - 'gdriveFolderRawAudio'
          - 'gdriveFolderFinishedAudio'
          - 'gdriveFolderTranscripts'
          - 'gdriveFolderCoverArt',
    '{gdriveFolderShowRecordings}',
    '"YOUR_FOLDER_ID_HERE"'
)
WHERE id = 1;
```

Replace `YOUR_FOLDER_ID_HERE` with the actual folder ID.

---

## Rebuild Asset Inventories

After updating the config:

1. Go to the Post-Production page.
2. Click **Refresh Assets**.
3. The scan will find each episode subfolder and populate all asset badges.
4. Episodes whose folder does not yet exist in Drive will show all `--` badges.
   That is correct — the folder just hasn't been created yet.

---

## Cleanup: Old Folders

Once all files are confirmed moved and inventories are rebuilding correctly,
you can delete (or archive) the now-empty old folders:
- `Raw Dog Recordings/`
- `Finished Episodes/`
- `Transcripts/`
- `Cover Art/`

Do not delete them until scanning has been verified working (see Phase 3).
