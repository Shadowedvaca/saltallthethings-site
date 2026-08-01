"""Validation and normalization rules for the private Song Bank."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlsplit
import re


_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
}
_SHORT_YOUTUBE_HOSTS = {"youtu.be", "www.youtu.be"}
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")


class SongContractError(ValueError):
    """Raised when Song Bank data cannot satisfy the browser contract."""


def _required_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str):
        raise SongContractError(f"{label} must be a string")
    text = value.strip()
    if not text:
        raise SongContractError(f"{label} must not be empty")
    return text


def validate_youtube_url(value: Any) -> str:
    """Validate a YouTube video URL locally without making a network request."""
    url = _required_text(value, label="youtubeUrl")
    try:
        parsed = urlsplit(url)
    except ValueError as error:
        raise SongContractError("youtubeUrl must be a valid YouTube URL") from error

    try:
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as error:
        raise SongContractError("youtubeUrl must be a valid YouTube URL") from error
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or host not in _YOUTUBE_HOSTS | _SHORT_YOUTUBE_HOSTS
    ):
        raise SongContractError("youtubeUrl must use an official HTTPS YouTube host")

    path_parts = [part for part in parsed.path.split("/") if part]
    video_id: str | None = None
    if host in _SHORT_YOUTUBE_HOSTS:
        if len(path_parts) == 1:
            video_id = path_parts[0]
    elif parsed.path.rstrip("/") == "/watch":
        values = parse_qs(parsed.query).get("v", [])
        if len(values) == 1:
            video_id = values[0]
    elif len(path_parts) == 2 and path_parts[0] in {"shorts", "live", "embed"}:
        video_id = path_parts[1]

    if video_id is None or not _VIDEO_ID_RE.fullmatch(video_id):
        raise SongContractError(
            "youtubeUrl must identify a YouTube watch, short, live, embed, or youtu.be video"
        )
    return url


def validate_banked_songs(value: Any) -> list[dict]:
    """Return canonical Song Bank records or reject ambiguous lifecycle data."""
    if not isinstance(value, list):
        raise SongContractError("songs must be an array")

    song_ids: set[str] = set()
    assigned_ideas: set[str] = set()
    canonical: list[dict] = []
    for index, song in enumerate(value, start=1):
        if not isinstance(song, dict):
            raise SongContractError(f"banked song {index} must be an object")

        song_id = _required_text(song.get("id"), label=f"banked song {index} id")
        if song_id in song_ids:
            raise SongContractError(f"banked song {index} duplicates another song id")
        song_ids.add(song_id)

        artist = _required_text(song.get("artist"), label=f"banked song {index} artist")
        title = _required_text(song.get("title"), label=f"banked song {index} title")
        youtube_url = validate_youtube_url(song.get("youtubeUrl"))

        private_notes = song.get("privateNotes", "")
        if private_notes is None:
            private_notes = ""
        if not isinstance(private_notes, str):
            raise SongContractError(f"banked song {index} privateNotes must be a string")
        private_notes = private_notes.strip()

        status = song.get("status") or "unused"
        if status not in {"unused", "used", "retired"}:
            raise SongContractError(
                f"banked song {index} has unsupported status {status!r}"
            )

        idea_id = song.get("assignedIdeaId")
        if status == "used":
            idea_id = _required_text(
                idea_id, label=f"banked song {index} assignedIdeaId"
            )
            if idea_id in assigned_ideas:
                raise SongContractError("only one used song may be assigned to an idea")
            assigned_ideas.add(idea_id)
        else:
            idea_id = None

        canonical.append(
            {
                **song,
                "id": song_id,
                "artist": artist,
                "title": title,
                "youtubeUrl": youtube_url,
                "privateNotes": private_notes,
                "status": status,
                "assignedIdeaId": idea_id,
            }
        )
    return canonical
