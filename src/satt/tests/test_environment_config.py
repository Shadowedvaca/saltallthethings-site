"""Environment isolation and browser-origin regression tests."""

from pathlib import Path

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from satt.config import Settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ENVIRONMENT_SENSITIVE_BROWSER_FILES = (
    "config.html",
    "index.html",
    "login.html",
    "register.html",
    "songs.html",
    "js/ai-service.js",
    "js/postproduction.js",
    "js/site-config.js",
    "js/show-song.js",
    "js/songs.js",
    "js/storage.js",
)
PRODUCTION_API_MARKERS = (
    "https://saltallthethings.com/api",
    "https://saltallthethings.com/public",
    "https://www.saltallthethings.com/api",
    "https://www.saltallthethings.com/public",
    "https://salt.shadowedvaca.com/api",
)


def test_browser_api_calls_do_not_embed_production_origins():
    for relative_path in ENVIRONMENT_SENSITIVE_BROWSER_FILES:
        source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
        for marker in PRODUCTION_API_MARKERS:
            assert marker not in source, f"{relative_path} embeds {marker}"


def test_browser_api_calls_use_same_origin_paths():
    assert "_apiUrl: '/api'" in (
        REPOSITORY_ROOT / "js/storage.js"
    ).read_text(encoding="utf-8")
    assert "const API_BASE = '/api'" in (
        REPOSITORY_ROOT / "js/ai-service.js"
    ).read_text(encoding="utf-8")
    assert "_apiBase: '/api'" in (
        REPOSITORY_ROOT / "js/postproduction.js"
    ).read_text(encoding="utf-8")
    assert "publicApiUrl: window.location.origin" in (
        REPOSITORY_ROOT / "js/site-config.js"
    ).read_text(encoding="utf-8")


def test_database_environment_must_match_application_environment():
    with pytest.raises(ValidationError, match="DATABASE_ENVIRONMENT must match"):
        Settings(environment="development", database_environment="production")


@pytest.mark.parametrize("field", ["site_url", "cors_origins"])
def test_nonproduction_rejects_production_origins(field: str):
    values = {
        "environment": "development",
        "database_environment": "development",
        field: "https://saltallthethings.com",
    }
    with pytest.raises(ValidationError, match="must not target production"):
        Settings(**values)


def test_nonproduction_google_credentials_require_explicit_opt_in():
    values = {
        "environment": "test",
        "database_environment": "test",
        "site_url": "https://test.saltallthethings.com",
        "cors_origins": "https://test.saltallthethings.com",
        "google_oauth_client_id": "configured-value",
    }
    with pytest.raises(ValidationError, match="explicit external-service opt-in"):
        Settings(**values)

    settings = Settings(
        **values,
        allow_nonproduction_external_services=True,
    )
    assert settings.environment == "test"


@pytest.mark.parametrize(
    ("environment", "origin"),
    [
        ("local", "http://localhost:8200"),
        ("development", "https://dev.saltallthethings.com"),
        ("test", "https://test.saltallthethings.com"),
        ("production", "https://saltallthethings.com"),
    ],
)
def test_canonical_environment_origins_are_valid(environment: str, origin: str):
    settings = Settings(
        environment=environment,
        database_environment=environment,
        site_url=origin,
        cors_origins=origin,
    )
    assert settings.site_url == origin


@pytest.mark.asyncio
async def test_local_server_exposes_public_frontend_but_not_environment_file(
    client: AsyncClient,
):
    page_response = await client.get("/login.html")
    song_page_response = await client.get("/songs.html")
    script_response = await client.get("/js/storage.js")
    environment_response = await client.get("/.env")

    assert page_response.status_code == 200
    assert song_page_response.status_code == 200
    assert "Song Bank" in song_page_response.text
    assert script_response.status_code == 200
    assert environment_response.status_code == 404
