"""Private database URL and production host normalization tests."""

import os

import pytest

from satt.database_url import configure_database_url
from scripts import production_backup


def test_private_container_fields_build_an_encoded_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SATT_DB_HOST", "database")
    monkeypatch.setenv("SATT_DB_PORT", "5432")
    monkeypatch.setenv("SATT_DB_NAME", "satt data")
    monkeypatch.setenv("SATT_DB_USER", "service user")
    monkeypatch.setenv("SATT_DB_PASSWORD", "secret/value")

    database_url = configure_database_url(require_private=True)

    assert database_url == (
        "postgresql+asyncpg://service%20user:secret%2Fvalue@"
        "database:5432/satt%20data"
    )
    assert os.environ["DATABASE_URL"] == database_url


def test_existing_database_url_is_preserved(monkeypatch):
    configured = "postgresql+asyncpg://configured:secret@127.0.0.1/satt"
    monkeypatch.setenv("DATABASE_URL", configured)
    for name in (
        "SATT_DB_HOST",
        "SATT_DB_PORT",
        "SATT_DB_NAME",
        "SATT_DB_USER",
        "SATT_DB_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)

    assert configure_database_url(require_private=True) == configured


def test_incomplete_private_database_configuration_is_rejected(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SATT_DB_HOST", "database")
    monkeypatch.setenv("SATT_DB_PORT", "5432")
    monkeypatch.setenv("SATT_DB_NAME", "satt")
    monkeypatch.setenv("SATT_DB_USER", "service")
    monkeypatch.delenv("SATT_DB_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="configuration is incomplete"):
        configure_database_url(require_private=True)


def test_host_fingerprint_maps_only_the_allowed_alias_to_loopback():
    database_url = (
        "postgresql+asyncpg://host.docker.internal-user:sensitive-value@"
        "host.docker.internal:5432/satt"
    )

    runtime_url = production_backup.host_runtime_database_url(database_url)

    assert runtime_url == (
        "postgresql+asyncpg://host.docker.internal-user:sensitive-value@"
        "127.0.0.1:5432/satt"
    )


def test_host_fingerprint_refuses_an_external_database_host():
    with pytest.raises(
        production_backup.ProductionBackupError,
        match="refuses a non-local database host",
    ):
        production_backup.host_runtime_database_url(
            "postgresql://service-user:sensitive-value@database.example/satt"
        )
