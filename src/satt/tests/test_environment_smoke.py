"""Safety tests for the non-production deployment smoke helper."""

from unittest.mock import patch
from pathlib import Path

import pytest

from satt.scripts.environment_smoke import (
    SmokeFailure,
    _contains_forbidden_key,
    validate_target,
)


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


def test_top3_smoke_checks_response_keys_not_legitimate_concept_prose():
    concept_bank = {
        "concepts": [
            {
                "rules": "Exactly three distinct picks.",
                "assignedEpisodes": [{"title": "Picking favorites"}],
            }
        ]
    }
    assert not _contains_forbidden_key(
        concept_bank, {"picks", "privateDiscussionNotes"}
    )
    concept_bank["concepts"][0]["submission"] = {"picks": ["A", "B", "C"]}
    assert _contains_forbidden_key(
        concept_bank, {"picks", "privateDiscussionNotes"}
    )


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
    assert '"/show_management.html"' in source
    assert '"/top3.html"' in source
    assert '"/js/show-song.js"' in source
    assert '"/js/episode-overview.js"' in source
    assert '"/js/songs.js"' in source
    assert '"/js/top3-bank.js"' in source
    assert '"/js/top3-episode.js"' in source
    assert '"validateSongInput" in response.text' in source
    assert '"renderPreparation" in response.text' in source
    assert '"publicSongBlock" in response.text' in source
    assert '"publicTop3Block" in response.text' in source
    assert '"clipboard.writeText" in response.text' in source
    assert '"conceptCardMarkup" in response.text' in source
    assert '"Top3EpisodePlanning" in response.text' in source
    assert '"Top 3 preparation" in response.text' in source
    assert '"Top3EpisodePlanning.render" in response.text' in source
    assert '"Top3EpisodePlanning.summaryMarkup" in response.text' in source
    assert '"/ai/top3-concept" in response.text' in source
    assert "/api/top3/concepts" in source
    assert "/api/top3/episodes/{idea_id}/submission" in source
    assert "/api/top3/episodes/{idea_id}/reveals/{submission_id}" in source
    assert "/api/top3/episodes/{idea_id}/external-submissions" in source
    assert "/api/top3/episodes/{idea_id}/spotify-results" in source
    assert (
        "Top 3 Spotify result was not the narrow exact-three contributor contract"
        in source
    )
    assert (
        "Top 3 Spotify result did not keep the viewer's proper-case account before external results"
        in source
    )
    assert "Top 3 Spotify result exposed another host before viewer reveal" in source
    assert "Top 3 Spotify composition unexpectedly changed the data revision" in source
    assert "Spotify composition revealed a hidden list in preparation state" in source
    assert "Top 3 Spotify result ordering or content was not deterministic" in source
    assert "repeated reveal changed revision or audit timestamp" in source
    assert "viewer-specific reveal leaked in the opposite direction" in source
    assert "external Top 3 edit changed immutable entry attribution" in source
    assert "external Top 3 account-owner spoof" in source
    assert "another user received a private pick" in source
    assert "general export unexpectedly contains Top 3 data" in source
    assert "replacement retained picks from the prior concept" in source
    assert "owner edit did not persist" in source
    assert "removed Top 3 assignment survived viewer reload" in source
    assert "Top 3 Bank did not report assignment metadata" in source
    assert "Top 3 Bank edit and retirement" in source
    assert "Top 3 Bank restoration" in source
    assert "deleted Top 3 concept survived reload" in source
    assert '"/api/ai/top3-concept"' in source
    assert "participant-shaped Top 3 AI input" in source
    assert "Top 3 AI missing credential" in source
    assert '"claudeApiKey" not in config' in source
    assert '"openaiApiKey" not in config' in source
