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
        print(f"[transcribe-auto] Running WhisperX on: {os.path.basename(audio_path)}")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            return False

        # WhisperX names the JSON after the input filename (without extension)
        whisperx_name = os.path.splitext(os.path.basename(audio_path))[0] + ".json"
        whisperx_out = os.path.join(tmp, whisperx_name)
        target_json = os.path.join(output_dir, f"Transcript_{key}.json")

        if not os.path.isfile(whisperx_out):
            print(f"[transcribe-auto] ERROR: WhisperX JSON not found: {whisperx_out}")
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

    # Output goes to the same folder as the audio file
    output_dir = os.path.dirname(audio_path)
    key = _extract_key(audio_path)
    json_out = os.path.join(output_dir, f"Transcript_{key}.json")
    txt_out = os.path.join(output_dir, f"Transcript_{key}.txt")

    # Step 1: WhisperX
    if not transcribe(audio_path, hf_token, output_dir, key):
        print(f"[transcribe-auto] ERROR: WhisperX failed on {os.path.basename(audio_path)}")
        sys.exit(1)

    if not os.path.isfile(json_out):
        print(f"[transcribe-auto] ERROR: Expected JSON not found at {json_out}")
        sys.exit(1)

    # Step 2: Label speakers
    if not label_speakers(json_out, txt_out):
        print(f"[transcribe-auto] ERROR: Speaker labeling failed. Raw JSON kept at {json_out}")
        sys.exit(1)

    print(f"[transcribe-auto] Done: Transcript_{key}.txt")

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
