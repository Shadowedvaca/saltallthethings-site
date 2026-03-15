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
