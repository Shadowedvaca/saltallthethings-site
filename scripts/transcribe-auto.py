"""
transcribe-auto.py - Non-interactive transcription for a single audio file.

Usage:
    python scripts/transcribe-auto.py <audio_file_path> [--notify-server]

Called by the watcher after a new file lands in Google Drive. Runs WhisperX
with diarization, then calls label-speakers.py --auto to assign speaker names
without user interaction. Optionally notifies the server to refresh asset
inventory.
"""

import argparse
import os
import subprocess
import sys

# ── Folder paths ────────────────────────────────────────────────────────────
SHARED_ROOT = r"J:\Shared drives\Salt All The Things\Show Recordings"
RAW_DIR = SHARED_ROOT + r"\Raw Dog Recordings"
FINISHED_DIR = SHARED_ROOT + r"\Finished Episodes"
TRANSCRIPTS_DIR = SHARED_ROOT + r"\Transcripts"

WHISPERX_MODEL = "medium"
DEFAULT_HOSTS = ["Rocket", "Trog"]

# Script paths (relative to repo root, resolved at runtime)
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
LABEL_SCRIPT = os.path.join(_SCRIPTS_DIR, "label-speakers.py")


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
            return data.get("access_token")
    except urllib.error.HTTPError as e:
        print(f"[transcribe-auto] Login failed: HTTP {e.code}")
    except Exception as e:
        print(f"[transcribe-auto] Login error: {e}")
    return None


def transcribe(audio_path, hf_token):
    """Run WhisperX on audio_path, output JSON to TRANSCRIPTS_DIR."""
    cmd = [
        "whisperx", audio_path,
        "--model", WHISPERX_MODEL,
        "--language", "en",
        "--compute_type", "int8",
        "--diarize",
        "--hf_token", hf_token,
        "--output_format", "json",
        "--output_dir", TRANSCRIPTS_DIR,
    ]
    print(f"[transcribe-auto] Running WhisperX on: {os.path.basename(audio_path)}")
    result = subprocess.run(cmd)
    return result.returncode == 0


def label_speakers(json_path, txt_path):
    """Run label-speakers.py --auto to produce a labeled transcript."""
    cmd = [
        sys.executable, LABEL_SCRIPT,
        json_path, txt_path,
        "--hosts", *DEFAULT_HOSTS,
        "--auto",
    ]
    print(f"[transcribe-auto] Labeling speakers -> {os.path.basename(txt_path)}")
    result = subprocess.run(cmd)
    return result.returncode == 0


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
            print(f"[transcribe-auto] Server notified: HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        print(f"[transcribe-auto] Server notification failed: HTTP {e.code}")
    except Exception as e:
        print(f"[transcribe-auto] Server notification error: {e}")


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

    # Validate input
    if not os.path.isfile(audio_path):
        print(f"[transcribe-auto] ERROR: File not found: {audio_path}")
        sys.exit(1)

    ext = os.path.splitext(audio_path)[1].lower()
    if ext not in (".wav", ".mp3"):
        print(f"[transcribe-auto] ERROR: Unsupported file type '{ext}' — must be .wav or .mp3")
        sys.exit(1)

    hf_token, satt_username, satt_password = load_secrets()
    if not hf_token:
        print("[transcribe-auto] ERROR: HF_TOKEN not set. Add it to scripts/secrets.py or environment.")
        sys.exit(1)

    os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

    basename = os.path.splitext(os.path.basename(audio_path))[0]
    json_out = os.path.join(TRANSCRIPTS_DIR, basename + ".json")
    txt_out = os.path.join(TRANSCRIPTS_DIR, basename + ".txt")

    # Step 1: WhisperX
    if not transcribe(audio_path, hf_token):
        print(f"[transcribe-auto] ERROR: WhisperX failed on {os.path.basename(audio_path)}")
        sys.exit(1)

    if not os.path.isfile(json_out):
        print(f"[transcribe-auto] ERROR: Expected JSON not found at {json_out}")
        sys.exit(1)

    # Step 2: Label speakers
    if not label_speakers(json_out, txt_out):
        print(f"[transcribe-auto] ERROR: Speaker labeling failed. Raw JSON kept at {json_out}")
        sys.exit(1)

    print(f"[transcribe-auto] Done: {basename}.txt")

    # Step 3: Notify server (optional)
    if args.notify_server:
        if not satt_username or not satt_password:
            print("[transcribe-auto] WARNING: --notify-server set but SATT_USERNAME/SATT_PASSWORD not found in secrets.py. Skipping.")
        else:
            print("[transcribe-auto] Logging in to get fresh token...")
            token = get_jwt(satt_username, satt_password)
            if token:
                notify_server(token)
            else:
                print("[transcribe-auto] Could not obtain token — server not notified.")


if __name__ == "__main__":
    main()
