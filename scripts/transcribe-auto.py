"""
transcribe-auto.py - Non-interactive transcription for a single audio file.

Usage:
    python scripts/transcribe-auto.py <audio_file_path> [--notify-server]

Called by the watcher after a new file lands in Google Drive. Runs WhisperX
with diarization, then calls label-speakers.py --auto to assign speaker names
without user interaction. Optionally notifies the server to refresh asset
inventory.

Output files are written to the same folder as the audio file, prefixed with
Transcript_. The production key is extracted from the filename:
  Raw_Dog_{key}.wav  ->  key = {key}
  {key}.mp3          ->  key = {key}
"""

import argparse
import logging
import logging.handlers
import os
import shutil
import subprocess
import sys
import tempfile

# ── Folder paths ────────────────────────────────────────────────────────────
SHARED_ROOT = r"J:\Shared drives\Salt All The Things\Show Recordings"

WHISPERX_MODEL = "medium"
DEFAULT_HOSTS = ["Rocket", "Trog"]

# Script paths (relative to repo root, resolved at runtime)
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
LABEL_SCRIPT = os.path.join(_SCRIPTS_DIR, "label-speakers.py")

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_FILE = os.path.join(_SCRIPTS_DIR, "satt-watcher.log")


def _setup_logging(name: str) -> logging.Logger:
    _log = logging.getLogger(name)
    _log.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    _log.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    _log.addHandler(sh)
    return _log


log = _setup_logging("transcribe")


def load_secrets():
    """Load HF_TOKEN, SATT_USERNAME, SATT_PASSWORD from scripts/secrets.py or environment."""
    hf_token = os.environ.get("HF_TOKEN", "")
    satt_username = os.environ.get("SATT_USERNAME", "")
    satt_password = os.environ.get("SATT_PASSWORD", "")

    secrets_path = os.path.join(_SCRIPTS_DIR, "secrets.py")
    if os.path.isfile(secrets_path):
        ns = {}
        with open(secrets_path, "r", encoding="utf-8") as f:
            exec(compile(f.read(), secrets_path, "exec"), ns)
        hf_token = hf_token or ns.get("HF_TOKEN", "")
        satt_username = satt_username or ns.get("SATT_USERNAME", "")
        satt_password = satt_password or ns.get("SATT_PASSWORD", "")

    return hf_token, satt_username, satt_password


def get_jwt(username, password):
    """Log in to the site and return a fresh JWT token."""
    import json
    import urllib.request
    import urllib.error

    url = "https://saltallthethings.com/api/auth/login"
    payload = json.dumps({"username": username, "password": password}).encode()
    req = urllib.request.Request(
        url,
        method="POST",
        headers={"Content-Type": "application/json"},
        data=payload,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            token = data.get("token")
            if not token:
                log.error("Login succeeded but response has no token: %s", data)
            return token
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        log.error("Login failed: HTTP %s — %s", e.code, body)
    except Exception as e:
        log.exception("Login error: %s", e)
    return None


def _extract_key(audio_path: str) -> str:
    """Extract the production key from an audio filename.

    Raw_Dog_{key}.wav  ->  {key}
    {key}.mp3          ->  {key}
    """
    name = os.path.splitext(os.path.basename(audio_path))[0]
    if name.lower().startswith("raw_dog_"):
        return name[len("Raw_Dog_"):]
    return name


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
        log.info("Running WhisperX on: %s", os.path.basename(audio_path))
        result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            log.error("WhisperX exited with code %d", result.returncode)
            if result.stderr:
                log.error("WhisperX stderr: %s", result.stderr.strip())
            return False

        # WhisperX names the JSON after the input filename (without extension)
        whisperx_name = os.path.splitext(os.path.basename(audio_path))[0] + ".json"
        whisperx_out = os.path.join(tmp, whisperx_name)
        target_json = os.path.join(output_dir, f"Transcript_{key}.json")

        if not os.path.isfile(whisperx_out):
            log.error("WhisperX JSON not found: %s", whisperx_out)
            return False

        shutil.move(whisperx_out, target_json)
    return True


def label_speakers(json_path, txt_path):
    """Run label-speakers.py --auto to produce a labeled transcript."""
    cmd = [
        sys.executable, LABEL_SCRIPT,
        json_path, txt_path,
        "--hosts", *DEFAULT_HOSTS,
        "--auto",
    ]
    log.info("Labeling speakers -> %s", os.path.basename(txt_path))
    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        log.error("label-speakers exited with code %d", result.returncode)
        if result.stderr:
            log.error("label-speakers stderr: %s", result.stderr.strip())
        return False
    return True


def notify_server(token):
    """POST to the server scan endpoint to refresh asset inventory."""
    import urllib.request
    import urllib.error

    url = "https://saltallthethings.com/api/postproduction/scan"
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        data=b"{}",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            log.info("Server notified: HTTP %s", resp.status)
    except urllib.error.HTTPError as e:
        log.error("Server notification failed: HTTP %s", e.code)
    except Exception as e:
        log.exception("Server notification error: %s", e)


def main():
    parser = argparse.ArgumentParser(
        description="Non-interactive transcription for a single audio file."
    )
    parser.add_argument("audio_file", help="Path to the WAV or MP3 file to transcribe")
    parser.add_argument(
        "--notify-server",
        action="store_true",
        help="After transcription, POST to the server scan endpoint",
    )
    args = parser.parse_args()

    audio_path = os.path.abspath(args.audio_file)
    log.info("=== transcribe-auto starting: %s ===", os.path.basename(audio_path))

    # Validate input
    if not os.path.isfile(audio_path):
        log.error("File not found: %s", audio_path)
        sys.exit(1)

    ext = os.path.splitext(audio_path)[1].lower()
    if ext not in (".wav", ".mp3"):
        log.error("Unsupported file type '%s' — must be .wav or .mp3", ext)
        sys.exit(1)

    hf_token, satt_username, satt_password = load_secrets()
    if not hf_token:
        log.error("HF_TOKEN not set. Add it to scripts/secrets.py or environment.")
        sys.exit(1)

    # Output goes to the same folder as the audio file
    output_dir = os.path.dirname(audio_path)
    key = _extract_key(audio_path)
    json_out = os.path.join(output_dir, f"Transcript_{key}.json")
    txt_out = os.path.join(output_dir, f"Transcript_{key}.txt")

    # Step 1: WhisperX
    if not transcribe(audio_path, hf_token, output_dir, key):
        log.error("WhisperX failed on %s — exiting.", os.path.basename(audio_path))
        sys.exit(1)

    if not os.path.isfile(json_out):
        log.error("Expected JSON not found at %s", json_out)
        sys.exit(1)

    # Step 2: Label speakers
    if not label_speakers(json_out, txt_out):
        log.error("Speaker labeling failed. Raw JSON kept at %s", json_out)
        sys.exit(1)

    log.info("Done: Transcript_%s.txt", key)

    # Step 3: Notify server (optional)
    if args.notify_server:
        if not satt_username or not satt_password:
            log.warning("--notify-server set but SATT_USERNAME/SATT_PASSWORD not found in secrets.py. Skipping.")
        else:
            log.info("Logging in to get fresh token...")
            token = get_jwt(satt_username, satt_password)
            if token:
                notify_server(token)
            else:
                log.error("Could not obtain token — server not notified.")

    log.info("=== transcribe-auto complete: %s ===", os.path.basename(audio_path))


if __name__ == "__main__":
    main()
