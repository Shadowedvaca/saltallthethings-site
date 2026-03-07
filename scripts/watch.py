"""
watch.py - Folder watcher for automatic transcription.

Watches Google Drive synced folders for new audio files and triggers
transcription automatically. Runs as a background process on the recording PC.

Usage:
    python scripts/watch.py

Add to Windows startup via Task Scheduler or a .bat wrapper to run on boot.

Requires:
    pip install watchdog
"""

import os
import subprocess
import sys
import threading
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# ── Folder paths ────────────────────────────────────────────────────────────
SHARED_ROOT = r"J:\Shared drives\Salt All The Things\Show Recordings"
RAW_DIR = SHARED_ROOT + r"\Raw Dog Recordings"
FINISHED_DIR = SHARED_ROOT + r"\Finished Episodes"
TRANSCRIPTS_DIR = SHARED_ROOT + r"\Transcripts"

# How long to wait after a file appears before starting transcription.
# Allows large files time to finish syncing from Drive before we touch them.
SYNC_SETTLE_SECONDS = 30

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
TRANSCRIBE_SCRIPT = os.path.join(_SCRIPTS_DIR, "transcribe-auto.py")


def run_transcription(audio_path):
    """Spawn transcribe-auto.py for a single audio file in a subprocess."""
    cmd = [sys.executable, TRANSCRIBE_SCRIPT, audio_path, "--notify-server"]
    print(f"[watch] Starting transcription: {os.path.basename(audio_path)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"[watch] ERROR: transcription failed for {os.path.basename(audio_path)}")
    else:
        print(f"[watch] Transcription complete: {os.path.basename(audio_path)}")


def schedule_transcription(audio_path, delay=SYNC_SETTLE_SECONDS):
    """Wait for sync to settle, then run transcription in a background thread."""
    def _run():
        print(f"[watch] Waiting {delay}s for sync to settle: {os.path.basename(audio_path)}")
        time.sleep(delay)
        run_transcription(audio_path)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


class RawRecordingsHandler(FileSystemEventHandler):
    """Watches Raw Dog Recordings for new WAV files."""

    def on_created(self, event):
        if event.is_directory:
            return
        path = event.src_path
        if path.lower().endswith(".wav"):
            print(f"[watch] New raw recording detected: {os.path.basename(path)}")
            schedule_transcription(path)


class FinishedEpisodesHandler(FileSystemEventHandler):
    """Watches Finished Episodes for new MP3 files."""

    def on_created(self, event):
        if event.is_directory:
            return
        path = event.src_path
        if path.lower().endswith(".mp3"):
            basename = os.path.splitext(os.path.basename(path))[0]
            existing_txt = os.path.join(TRANSCRIPTS_DIR, basename + ".txt")
            if os.path.isfile(existing_txt):
                print(f"[watch] Finished episode arrived, replacing transcript for: {basename}")
            else:
                print(f"[watch] New finished episode detected: {os.path.basename(path)}")
            schedule_transcription(path)


def main():
    for folder, label in [(RAW_DIR, "Raw Dog Recordings"), (FINISHED_DIR, "Finished Episodes")]:
        if not os.path.isdir(folder):
            print(f"[watch] WARNING: folder not found: {folder}")
            print(f"[watch]   ({label} — is Google Drive for Desktop running?)")

    observer = Observer()
    observer.schedule(RawRecordingsHandler(), RAW_DIR, recursive=False)
    observer.schedule(FinishedEpisodesHandler(), FINISHED_DIR, recursive=False)
    observer.start()

    print("[watch] Watcher started.")
    print(f"[watch]   Watching: {RAW_DIR}")
    print(f"[watch]   Watching: {FINISHED_DIR}")
    print("[watch] Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[watch] Stopping...")
        observer.stop()

    observer.join()
    print("[watch] Stopped.")


if __name__ == "__main__":
    main()
