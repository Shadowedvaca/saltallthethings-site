"""Pure transcription-job lease and browser-payload helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


TRANSCRIPTION_LEASE_SECONDS = 180


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def parse_job_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def transcription_lease_deadline(job: dict | None) -> datetime | None:
    """Return the explicit lease deadline, with bounded legacy compatibility."""
    if not job or job.get("status") != "in_progress":
        return None
    explicit = parse_job_datetime(job.get("leaseExpiresAt"))
    if explicit is not None:
        return explicit
    legacy_update = parse_job_datetime(job.get("updatedAt"))
    if legacy_update is None:
        return None
    return legacy_update + timedelta(seconds=TRANSCRIPTION_LEASE_SECONDS)


def is_transcription_job_stale(
    job: dict | None, *, now: datetime | None = None
) -> bool:
    deadline = transcription_lease_deadline(job)
    return deadline is not None and deadline <= (now or utc_now())


def public_transcription_job(
    job: dict | None, *, now: datetime | None = None
) -> dict | None:
    """Remove claim authority while retaining useful recovery metadata."""
    if job is None:
        return None
    public = {key: value for key, value in job.items() if key != "claimToken"}
    public["isStale"] = is_transcription_job_stale(job, now=now)
    return public
