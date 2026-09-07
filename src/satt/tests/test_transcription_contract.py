"""Pure tests for the transcription lease and public metadata contract."""

from datetime import datetime, timedelta, timezone

from satt.transcription import (
    TRANSCRIPTION_LEASE_SECONDS,
    is_transcription_job_stale,
    public_transcription_job,
    transcription_lease_deadline,
)


NOW = datetime(2026, 9, 7, 18, 0, tzinfo=timezone.utc)


def test_explicit_lease_defines_staleness():
    active = {
        "status": "in_progress",
        "leaseExpiresAt": (NOW + timedelta(seconds=1)).isoformat(),
    }
    stale = {
        "status": "in_progress",
        "leaseExpiresAt": NOW.isoformat(),
    }
    assert not is_transcription_job_stale(active, now=NOW)
    assert is_transcription_job_stale(stale, now=NOW)


def test_legacy_in_progress_job_gets_bounded_deadline_from_updated_at():
    job = {"status": "in_progress", "updatedAt": NOW.isoformat()}
    assert transcription_lease_deadline(job) == NOW + timedelta(
        seconds=TRANSCRIPTION_LEASE_SECONDS
    )
    assert not is_transcription_job_stale(job, now=NOW)
    assert is_transcription_job_stale(
        job, now=NOW + timedelta(seconds=TRANSCRIPTION_LEASE_SECONDS)
    )


def test_missing_or_malformed_lease_is_not_declared_stale():
    assert not is_transcription_job_stale({"status": "in_progress"}, now=NOW)
    assert not is_transcription_job_stale(
        {"status": "in_progress", "leaseExpiresAt": "invalid"}, now=NOW
    )


def test_public_job_metadata_never_exposes_claim_token():
    public = public_transcription_job(
        {
            "status": "in_progress",
            "claimToken": "private-claim-authority",
            "claimedBy": "watcher-example",
            "leaseExpiresAt": NOW.isoformat(),
        },
        now=NOW,
    )
    assert public is not None
    assert "claimToken" not in public
    assert public["claimedBy"] == "watcher-example"
    assert public["isStale"] is True
