"""Version-contract tests."""

from pathlib import Path

from satt.main import app
from satt.version import APP_VERSION


def test_authoritative_version_matches_fastapi_metadata():
    assert APP_VERSION == "0.0.1"
    assert app.version == APP_VERSION


def test_release_note_filename_and_heading_match_version():
    repository_root = Path(__file__).resolve().parents[3]
    release_notes = repository_root / "docs" / "releases" / f"{APP_VERSION}.md"

    assert release_notes.is_file()
    assert release_notes.read_text(encoding="utf-8").splitlines()[0] == (
        f"# Salt All The Things {APP_VERSION}"
    )
