"""Version-contract tests."""

import importlib.util
from pathlib import Path

from satt.main import app
from satt.version import APP_VERSION


def test_unassigned_source_version_matches_fastapi_metadata():
    repository_root = Path(__file__).resolve().parents[3]
    assert APP_VERSION == (
        repository_root / "VERSION"
    ).read_text(encoding="utf-8").strip()
    assert app.version == APP_VERSION
    assert APP_VERSION == "unassigned"


def test_pending_release_records_use_version_neutral_heading():
    repository_root = Path(__file__).resolve().parents[3]
    pending = repository_root / "docs" / "releases" / "pending"
    assert list(pending.glob("*.md"))
    for release_notes in pending.glob("*.md"):
        assert release_notes.read_text(encoding="utf-8").splitlines()[0] == (
            "# Salt All The Things — Pending Release"
        )


def test_production_runtime_version_can_come_from_tag(monkeypatch):
    monkeypatch.setenv("SATT_VERSION", "1.2.3")
    version_path = Path(__file__).resolve().parents[1] / "version.py"
    spec = importlib.util.spec_from_file_location("satt_test_runtime_version", version_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.APP_VERSION == "1.2.3"
