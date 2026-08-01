"""Unit coverage for Song Bank validation and local-only URL checks."""

import socket

import pytest

from satt.song_contract import (
    SongContractError,
    validate_banked_songs,
    validate_youtube_url,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abcdefghijk",
        "https://youtu.be/abcdefghijk",
        "https://youtube.com/shorts/abcdefghijk",
        "https://music.youtube.com/watch?v=abcdefghijk&list=example",
        "https://www.youtube.com/live/abcdefghijk",
        "https://www.youtube.com/embed/abcdefghijk",
    ],
)
def test_supported_youtube_urls_validate_without_network(monkeypatch, url):
    def fail_network(*_args, **_kwargs):
        raise AssertionError("Song validation must not use the network")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    assert validate_youtube_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://www.youtube.com/watch?v=abcdefghijk",
        "https://example.com/watch?v=abcdefghijk",
        "https://youtube.com.example.com/watch?v=abcdefghijk",
        "https://user@youtube.com/watch?v=abcdefghijk",
        "https://youtube.com:444/watch?v=abcdefghijk",
        "https://youtube.com/watch",
        "https://youtu.be/",
        "not a url",
    ],
)
def test_unsupported_youtube_urls_are_rejected(url):
    with pytest.raises(SongContractError, match="youtubeUrl"):
        validate_youtube_url(url)


def test_song_contract_trims_text_and_preserves_private_notes():
    [song] = validate_banked_songs(
        [
            {
                "id": " song-one ",
                "artist": " Artist ",
                "title": " Title ",
                "youtubeUrl": " https://youtu.be/abcdefghijk ",
                "privateNotes": " private preparation only ",
                "status": "unused",
            }
        ]
    )
    assert song == {
        "id": "song-one",
        "artist": "Artist",
        "title": "Title",
        "youtubeUrl": "https://youtu.be/abcdefghijk",
        "privateNotes": "private preparation only",
        "status": "unused",
        "assignedIdeaId": None,
    }


@pytest.mark.parametrize("field", ["artist", "title"])
def test_song_contract_rejects_empty_required_text(field):
    song = {
        "id": "song-one",
        "artist": "Artist",
        "title": "Title",
        "youtubeUrl": "https://youtu.be/abcdefghijk",
    }
    song[field] = "   "
    with pytest.raises(SongContractError, match=field):
        validate_banked_songs([song])


def test_retired_song_is_canonicalized_as_unassigned():
    [song] = validate_banked_songs(
        [
            {
                "id": "song-one",
                "artist": "Artist",
                "title": "Title",
                "youtubeUrl": "https://youtu.be/abcdefghijk",
                "status": "retired",
                "assignedIdeaId": "stale-idea",
            }
        ]
    )
    assert song["assignedIdeaId"] is None


def test_only_one_used_song_may_reference_an_idea():
    base = {
        "artist": "Artist",
        "youtubeUrl": "https://youtu.be/abcdefghijk",
        "status": "used",
        "assignedIdeaId": "idea-one",
    }
    with pytest.raises(SongContractError, match="only one used song"):
        validate_banked_songs(
            [
                {**base, "id": "song-one", "title": "One"},
                {**base, "id": "song-two", "title": "Two"},
            ]
        )
