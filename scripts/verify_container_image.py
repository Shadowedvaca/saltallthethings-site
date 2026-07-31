"""Verify the built image contains no secret-bearing runtime configuration."""

from __future__ import annotations

import json
import subprocess

IMAGE = "satt:ci"
FORBIDDEN_ENVIRONMENT_PREFIXES = (
    "DATABASE_URL=",
    "SECRET_KEY=",
    "GOOGLE_OAUTH_",
    "SATT_DB_PASSWORD=",
)
FORBIDDEN_HISTORY_MARKERS = (
    "ci-only-database-placeholder",
    "ci-only-signing-placeholder-at-least-32-characters",
    "DATABASE_URL=",
    "GOOGLE_OAUTH_CLIENT_SECRET=",
    "SATT_DB_PASSWORD=",
)


def main() -> int:
    image_json = subprocess.check_output(
        ["docker", "image", "inspect", IMAGE],
        text=True,
    )
    image_data = json.loads(image_json)[0]
    configured_environment = image_data.get("Config", {}).get("Env", [])
    for item in configured_environment:
        if item.startswith(FORBIDDEN_ENVIRONMENT_PREFIXES):
            raise RuntimeError("Secret-bearing runtime configuration is embedded")

    history = subprocess.check_output(
        [
            "docker",
            "history",
            "--no-trunc",
            "--format",
            "{{.CreatedBy}}",
            IMAGE,
        ],
        text=True,
    )
    if any(marker in history for marker in FORBIDDEN_HISTORY_MARKERS):
        raise RuntimeError("Secret-bearing data is present in image history")

    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "python",
            IMAGE,
            "-c",
            (
                "from pathlib import Path; "
                "forbidden=['/app/.env','/app/.git','/app/settings-backup']; "
                "raise SystemExit(1 if any(Path(p).exists() for p in forbidden) else 0)"
            ),
        ],
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
