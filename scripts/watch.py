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

import json
import logging
import logging.handlers
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

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


SATT_API = "https://saltallthethings.com/api"
POLL_INTERVAL = 30  # seconds between job polls
TOKEN_REFRESH_INTERVAL = 4 * 3600  # re-login every 4 hours


def _load_credentials():
    """Load SATT_USERNAME and SATT_PASSWORD from secrets.py or environment."""
    username = os.environ.get("SATT_USERNAME", "")
    password = os.environ.get("SATT_PASSWORD", "")
    secrets_path = os.path.join(_SCRIPTS_DIR, "secrets.py")
    if os.path.isfile(secrets_path):
        ns: dict = {}
        with open(secrets_path, "r", encoding="utf-8") as f:
            exec(compile(f.read(), secrets_path, "exec"), ns)  # noqa: S102
        username = username or ns.get("SATT_USERNAME", "")
        password = password or ns.get("SATT_PASSWORD", "")
    return username, password


def _login(username: str, password: str) -> str | None:
    url = SATT_API + "/auth/login"
    payload = json.dumps({"username": username, "password": password}).encode()
    req = urllib.request.Request(
        url, method="POST", data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("token")
    except Exception:
        log.exception("Transcription poller: login failed")
        return None


def _api_get(url: str, token: str):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _api_put(url: str, token: str, body: dict):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, method="PUT", data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        log.error("API PUT %s failed: HTTP %s", url, e.code)
    except Exception:
        log.exception("API PUT %s failed", url)


def _find_audio_for_key(key: str) -> str | None:
    """Return the best audio file path for a production key, or None."""
    episode_dir = os.path.join(SHARED_ROOT, key)
    if not os.path.isdir(episode_dir):
        return None
    for filename in [f"Raw_Dog_{key}.wav", f"{key}.mp3"]:
        path = os.path.join(episode_dir, filename)
        if os.path.isfile(path):
            return path
    return None


def _run_transcription_job(slot_id: str, key: str, token: str) -> None:
    """Claim a pending transcription job, run it, and update its status."""
    # Mark in-progress
    _api_put(
        f"{SATT_API}/postproduction/{slot_id}/transcribe-status",
        token, {"status": "in_progress"},
    )

    audio_path = _find_audio_for_key(key)
    if not audio_path:
        msg = f"No audio file found in {SHARED_ROOT}/{key}/"
        log.error("Transcription job %s: %s", slot_id, msg)
        _api_put(
            f"{SATT_API}/postproduction/{slot_id}/transcribe-status",
            token, {"status": "failed", "error": msg},
        )
        return

    log.info("Transcription job %s: starting on %s", slot_id, os.path.basename(audio_path))
    cmd = [sys.executable, TRANSCRIBE_SCRIPT, audio_path, "--notify-server"]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        msg = f"transcribe-auto.py exited with code {result.returncode}"
        log.error("Transcription job %s: %s", slot_id, msg)
        _api_put(
            f"{SATT_API}/postproduction/{slot_id}/transcribe-status",
            token, {"status": "failed", "error": msg},
        )
    else:
        log.info("Transcription job %s: done", slot_id)
        _api_put(
            f"{SATT_API}/postproduction/{slot_id}/transcribe-status",
            token, {"status": "done"},
        )


def poll_transcription_jobs() -> None:
    """Background thread: poll the server for pending transcription jobs."""
    username, password = _load_credentials()
    if not username or not password:
        log.warning(
            "SATT_USERNAME/SATT_PASSWORD not set in secrets.py — "
            "manual transcription queuing from the UI will not work."
        )
        return

    token: str | None = None
    token_acquired_at = 0.0

    log.info("Transcription job poller started (poll interval: %ds)", POLL_INTERVAL)

    while True:
        try:
            now = time.time()
            if token is None or (now - token_acquired_at) > TOKEN_REFRESH_INTERVAL:
                token = _login(username, password)
                if token:
                    token_acquired_at = now
                    log.info("Transcription poller: logged in.")
                else:
                    log.error("Transcription poller: login failed, retrying in 60s.")
                    time.sleep(60)
                    continue

            jobs = _api_get(SATT_API + "/postproduction/transcription-jobs", token)
            for job in jobs:
                slot_id = job["slotId"]
                key = job["productionFileKey"]
                log.info("Transcription poller: job found — slot=%s key=%s", slot_id, key)
                _run_transcription_job(slot_id, key, token)

        except urllib.error.HTTPError as e:
            if e.code == 401:
                log.warning("Transcription poller: token expired, re-logging in.")
                token = None
            else:
                log.error("Transcription poller: HTTP %s", e.code)
        except Exception:
            log.exception("Transcription poller: unexpected error")

        time.sleep(POLL_INTERVAL)


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

    # Start background thread for UI-triggered transcription jobs
    t = threading.Thread(target=poll_transcription_jobs, daemon=True, name="job-poller")
    t.start()

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
