"""Secret-safe production backup and continuity tests."""

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from satt.scripts.production_fingerprint import fingerprint_rows
from scripts import production_backup


def test_backup_maps_container_host_to_loopback_without_echoing_credentials():
    database_url = (
        "postgresql+asyncpg://service-user:sensitive-value@"
        "host.docker.internal:5432/satt"
    )

    environment = production_backup.libpq_environment(database_url)

    assert environment == {
        "PGHOST": "127.0.0.1",
        "PGPORT": "5432",
        "PGDATABASE": "satt",
        "PGUSER": "service-user",
        "PGPASSWORD": "sensitive-value",
    }


def test_backup_refuses_an_external_database_host():
    with pytest.raises(
        production_backup.ProductionBackupError,
        match="refuses a non-local database host",
    ):
        production_backup.libpq_environment(
            "postgresql://service-user:sensitive-value@database.example/satt"
        )


def test_backup_is_created_verified_and_reported_only_by_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(command: list[str], environment: dict[str, str]) -> None:
        calls.append((command, environment))
        if command[0] == "pg_dump":
            output_path = Path(command[command.index("--file") + 1])
            output_path.write_bytes(b"verified-backup")

    monkeypatch.setattr(
        production_backup,
        "_run_without_sensitive_output",
        fake_run,
    )
    backup, digest = production_backup.create_verified_backup(
        "postgresql://service-user:sensitive-value@127.0.0.1/satt",
        tmp_path,
        "prod-v0.0.1",
        now=datetime(2026, 7, 30, tzinfo=UTC),
    )

    assert backup.name == "pre-deploy-prod-v0.0.1-20260730T000000Z.dump"
    assert len(digest) == 64
    assert [call[0][0] for call in calls] == ["pg_dump", "pg_restore"]
    assert all("sensitive-value" not in " ".join(command) for command, _ in calls)


def test_backup_main_never_prints_database_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_ENVIRONMENT", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://service-user:sensitive-value@127.0.0.1/satt",
    )
    monkeypatch.setattr(
        production_backup,
        "create_verified_backup",
        lambda *_args, **_kwargs: (tmp_path / "backup.dump", "a" * 64),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["production_backup.py", "--tag", "prod-v0.0.1"],
    )

    assert production_backup.main() == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result == {
        "file": "backup.dump",
        "sha256": "a" * 64,
        "verified": True,
    }
    assert "service-user" not in output
    assert "sensitive-value" not in output


def test_fingerprint_emits_only_counts_and_one_way_digest():
    result = fingerprint_rows(
        {
            "users": [
                {
                    "id": 1,
                    "username": "private-user",
                    "password_hash": "private-hash",
                }
            ]
        }
    )

    assert result["counts"] == {"users": 1}
    assert len(result["sha256"]) == 64
    serialized = json.dumps(result)
    assert "private-user" not in serialized
    assert "private-hash" not in serialized
