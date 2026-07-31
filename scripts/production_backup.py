"""Create and verify a secret-safe production PostgreSQL backup."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit, urlunsplit


TAG_PATTERN = re.compile(r"prod-v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")
LOCAL_DATABASE_HOSTS = {
    "127.0.0.1",
    "::1",
    "localhost",
    "host.docker.internal",
}


class ProductionBackupError(RuntimeError):
    """Raised when a production backup cannot be created safely."""


def libpq_environment(database_url: str) -> dict[str, str]:
    """Convert a local production URL to libpq variables without printing it."""

    normalized = database_url.replace(
        "postgresql+asyncpg://",
        "postgresql://",
        1,
    )
    parsed = urlsplit(normalized)
    host = parsed.hostname
    database = unquote(parsed.path.lstrip("/"))
    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")

    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ProductionBackupError("production backup requires PostgreSQL")
    if host not in LOCAL_DATABASE_HOSTS:
        raise ProductionBackupError(
            "production backup refuses a non-local database host"
        )
    if not all((database, user, password)):
        raise ProductionBackupError(
            "production database URL is missing required components"
        )

    # The container uses this stable host alias to reach the unchanged host
    # database. Host-side backup tools reach the same database on loopback.
    backup_host = "127.0.0.1" if host == "host.docker.internal" else host
    return {
        "PGHOST": backup_host,
        "PGPORT": str(parsed.port or 5432),
        "PGDATABASE": database,
        "PGUSER": user,
        "PGPASSWORD": password,
    }


def host_runtime_database_url(database_url: str) -> str:
    """Map the approved container host alias to host loopback for Python."""

    # Reuse backup validation so an external database can never be normalized
    # into an accepted production source.
    libpq_environment(database_url)
    parsed = urlsplit(database_url)
    if parsed.hostname != "host.docker.internal":
        return database_url

    userinfo, separator, host_port = parsed.netloc.rpartition("@")
    if not separator or not host_port.startswith("host.docker.internal"):
        raise ProductionBackupError("production database URL host is malformed")
    suffix = host_port[len("host.docker.internal") :]
    return urlunsplit(parsed._replace(netloc=f"{userinfo}@127.0.0.1{suffix}"))


def _run_without_sensitive_output(
    command: list[str], environment: dict[str, str]
) -> None:
    result = subprocess.run(
        command,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )
    if result.returncode:
        raise ProductionBackupError(
            f"{Path(command[0]).name} failed; inspect production locally"
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as backup_file:
        for chunk in iter(lambda: backup_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_verified_backup(
    database_url: str,
    backup_dir: Path,
    release_tag: str,
    *,
    phase: str,
    now: datetime | None = None,
) -> tuple[Path, str]:
    """Create a custom-format dump and verify its table of contents."""

    if not TAG_PATTERN.fullmatch(release_tag):
        raise ProductionBackupError("invalid production release tag")
    if phase not in {"preflight", "final"}:
        raise ProductionBackupError("invalid production backup phase")

    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.chmod(0o700)
    backup_path = backup_dir / f"{phase}-{release_tag}-{timestamp}.dump"
    if backup_path.exists():
        raise ProductionBackupError("refusing to overwrite a production backup")

    environment = os.environ.copy()
    environment.update(libpq_environment(database_url))
    _run_without_sensitive_output(
        [
            "pg_dump",
            "--format=custom",
            "--schema=satt",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(backup_path),
        ],
        environment,
    )
    if not backup_path.is_file() or backup_path.stat().st_size == 0:
        raise ProductionBackupError("production backup is empty")

    backup_path.chmod(0o600)
    _run_without_sensitive_output(
        ["pg_restore", "--list", str(backup_path)],
        environment,
    )
    fingerprint = _sha256_file(backup_path)
    return backup_path, fingerprint


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--phase", choices=("preflight", "final"), required=True)
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path("/opt/backups/satt-db/releases"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if os.environ.get("ENVIRONMENT") != "production":
        raise SystemExit("Production backup requires ENVIRONMENT=production")
    if os.environ.get("DATABASE_ENVIRONMENT") != "production":
        raise SystemExit("Production backup requires DATABASE_ENVIRONMENT=production")

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise SystemExit("Production backup requires DATABASE_URL")

    try:
        path, fingerprint = create_verified_backup(
            database_url,
            args.backup_dir,
            args.tag,
            phase=args.phase,
        )
    except ProductionBackupError as error:
        raise SystemExit(f"Production backup failed: {error}") from error

    print(
        json.dumps(
            {
                "file": path.name,
                "sha256": fingerprint,
                "verified": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
