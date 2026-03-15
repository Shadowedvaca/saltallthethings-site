"""
watch.py - Folder watcher for automatic transcription.

Watches the Show Recordings root folder recursively for new audio files
and triggers transcription automatically. Runs as a background process
on the recording PC.

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


def main():
    if not os.path.isdir(SHARED_ROOT):
        print(f"[watch] WARNING: folder not found: {SHARED_ROOT}")
        print("[watch]   (Show Recordings — is Google Drive for Desktop running?)")

    observer = Observer()
    observer.schedule(ShowRecordingsHandler(), SHARED_ROOT, recursive=True)
    observer.start()

    print("[watch] Watcher started.")
    print(f"[watch]   Watching recursively: {SHARED_ROOT}")
    print("[watch]   Triggers: Raw_Dog_*.wav, *.mp3")
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
