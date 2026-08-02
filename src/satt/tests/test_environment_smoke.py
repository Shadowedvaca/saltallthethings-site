"""Safety tests for the non-production deployment smoke helper."""

from unittest.mock import patch
from pathlib import Path

import pytest

from satt.scripts.environment_smoke import SmokeFailure, validate_target


def _settings(environment: str, database_environment: str, external: bool = False):
    return type(
        "SmokeSettings",
        (),
        {
            "environment": environment,
            "database_environment": database_environment,
            "allow_nonproduction_external_services": external,
        },
    )()


def test_smoke_accepts_matching_test_runtime_and_loopback_origin():
    with patch(
        "satt.scripts.environment_smoke.get_settings",
        return_value=_settings("test", "test"),
    ):
        validate_target("http://127.0.0.1:8200", "test")


@pytest.mark.parametrize(
    ("settings", "base_url", "expected_environment", "message"),
    [
        (
            _settings("production", "production"),
            "https://saltallthethings.com",
            "production",
            "restricted to development and test",
        ),
        (
            _settings("development", "development"),
            "http://127.0.0.1:8200",
            "test",
            "runtime environment does not match",
        ),
        (
            _settings("test", "production"),
            "http://127.0.0.1:8200",
            "test",
            "database ownership does not match",
        ),
        (
            _settings("test", "test"),
            "https://saltallthethings.com",
            "test",
            "production origins are forbidden",
        ),
        (
            _settings("test", "test"),
            "https://test.saltallthethings.com",
            "test",
            "may contact only the local application container",
        ),
        (
            _settings("test", "test", external=True),
            "http://127.0.0.1:8200",
            "test",
            "external-service opt-in must remain disabled",
        ),
    ],
)
def test_smoke_refuses_cross_tier_or_external_service_targets(
    settings, base_url, expected_environment, message
):
    with patch(
        "satt.scripts.environment_smoke.get_settings",
        return_value=settings,
    ):
        with pytest.raises(SmokeFailure, match=message):
            validate_target(base_url, expected_environment)


def test_deployment_smoke_exercises_song_lifecycle_without_external_services():
    source = (
        Path(__file__).resolve().parents[1] / "scripts" / "environment_smoke.py"
    ).read_text(encoding="utf-8")
    assert "/api/data/songs" in source
    assert "/api/songs/{song_ids[0]}/assignment" in source
    assert "/api/songs/{song_ids[1]}/status" in source
    assert "/api/ideas/{idea_id}" in source
    assert "private_sentinel not in public_episodes.text" in source
    assert "https://example.invalid/not-youtube" in source
    assert '"/songs.html"' in source
    assert '"/top3.html"' in source
    assert '"/js/show-song.js"' in source
    assert '"/js/episode-overview.js"' in source
    assert '"/js/songs.js"' in source
    assert '"/js/top3-bank.js"' in source
    assert '"validateSongInput" in response.text' in source
    assert '"renderPreparation" in response.text' in source
    assert '"publicSongBlock" in response.text' in source
    assert '"clipboard.writeText" in response.text' in source
    assert '"conceptCardMarkup" in response.text' in source
    assert '"/ai/top3-concept" in response.text' in source
    assert "/api/top3/concepts" in source
    assert "/api/top3/episodes/{idea_id}/submission" in source
    assert "another user received a private pick" in source
    assert "general export unexpectedly contains Top 3 data" in source
    assert "replacement retained picks from the prior concept" in source
    assert "Top 3 Bank did not report assignment metadata" in source
    assert "Top 3 Bank edit and retirement" in source
    assert "Top 3 Bank restoration" in source
    assert "deleted Top 3 concept survived reload" in source
    assert '"/api/ai/top3-concept"' in source
    assert "participant-shaped Top 3 AI input" in source
    assert "Top 3 AI missing credential" in source
    assert '"claudeApiKey" not in config' in source
    assert '"openaiApiKey" not in config' in source
