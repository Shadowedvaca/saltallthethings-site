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

Log file: scripts/satt-watcher.log (rotates at 5 MB, keeps 3 backups)
"""

import logging
import logging.handlers
import os
import subprocess
import sys
import threading
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# ── Logging ─────────────────────────────────────────────────────────────────
_SCRIPTS_DIR_EARLY = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(_SCRIPTS_DIR_EARLY, "satt-watcher.log")


def _setup_logging(name: str) -> logging.Logger:
    log = logging.getLogger(name)
    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    log.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    log.addHandler(sh)
    return log


log = _setup_logging("watch")

# ── Folder paths ────────────────────────────────────────────────────────────
SHARED_ROOT = r"J:\Shared drives\Salt All The Things\Show Recordings"

# How long to wait after a file appears before starting transcription.
# Allows large files time to finish syncing from Drive before we touch them.
SYNC_SETTLE_SECONDS = 30

# How often to poll for the Drive folder when it isn't available at startup.
DRIVE_POLL_INTERVAL = 60  # seconds

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
TRANSCRIBE_SCRIPT = os.path.join(_SCRIPTS_DIR, "transcribe-auto.py")


def wait_for_drive(path: str, interval: int = DRIVE_POLL_INTERVAL) -> None:
    """Block until the given path is a readable directory.

    Logs once when the folder is missing, then silently retries every
    `interval` seconds.  Returns as soon as the folder is available.
    """
    if os.path.isdir(path):
        return
    log.warning("Drive folder not found: %s", path)
    log.warning("Google Drive may not be mounted yet — retrying every %ds.", interval)
    while not os.path.isdir(path):
        time.sleep(interval)
    log.info("Drive folder is now available: %s", path)


def run_transcription(audio_path):
    """Spawn transcribe-auto.py for a single audio file in a subprocess."""
    name = os.path.basename(audio_path)
    cmd = [sys.executable, TRANSCRIBE_SCRIPT, audio_path, "--notify-server"]
    log.info("Starting transcription: %s", name)
    try:
        result = subprocess.run(cmd)
        if result.returncode != 0:
            log.error("Transcription failed (exit %d): %s", result.returncode, name)
        else:
            log.info("Transcription complete: %s", name)
    except Exception:
        log.exception("Unexpected error running transcription for %s", name)


def schedule_transcription(audio_path, delay=SYNC_SETTLE_SECONDS):
    """Wait for sync to settle, then run transcription in a background thread."""
    def _run():
        log.info("Waiting %ds for sync to settle: %s", delay, os.path.basename(audio_path))
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
            log.info("New raw recording detected: %s", name)
            schedule_transcription(path)
        elif name_lower.endswith(".mp3"):
            log.info("New finished episode detected: %s", name)
            schedule_transcription(path)


def _handle_unhandled_exception(exc_type, exc_value, exc_tb):
    """Log unhandled exceptions before the process dies."""
    log.critical("Unhandled exception — watcher is exiting", exc_info=(exc_type, exc_value, exc_tb))


def main():
    sys.excepthook = _handle_unhandled_exception

    log.info("=== SATT Transcription Watcher starting ===")

    wait_for_drive(SHARED_ROOT)

    observer = Observer()
    observer.schedule(ShowRecordingsHandler(), SHARED_ROOT, recursive=True)
    observer.start()

    log.info("Watching recursively: %s", SHARED_ROOT)
    log.info("Triggers: Raw_Dog_*.wav, *.mp3")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt received — stopping.")
        observer.stop()

    observer.join()
    log.info("=== Watcher stopped ===")


if __name__ == "__main__":
    main()
