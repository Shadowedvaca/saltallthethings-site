"""Late-bound release metadata validation contract tests."""

from pathlib import Path

import pytest

from scripts.validate_release import (
    ReleaseValidationError,
    render_release_notes,
    validate_release,
)


PENDING_NOTES = """# Salt All The Things — Pending Release

## Highlights

- A concrete release outcome.

## Fixes/Changes

- A concrete behavior change.

## Validation

- Automated checks passed.

## Deployment/Migrations

- No schema migration is required.

## Rollback

- Redeploy the previously validated tag.

## Known Limitations

- One documented limitation remains.
"""

HISTORICAL_NOTES = PENDING_NOTES.replace(
    "# Salt All The Things — Pending Release", "# Salt All The Things 1.2.2"
)

TEMPLATE = """# Salt All The Things — Pending Release

## Highlights

## Fixes/Changes

## Validation

## Deployment/Migrations

## Rollback

## Known Limitations
"""


def _release_repository(tmp_path: Path) -> Path:
    releases = tmp_path / "docs" / "releases"
    pending = releases / "pending"
    pending.mkdir(parents=True)
    (tmp_path / "VERSION").write_text("unassigned\n", encoding="utf-8")
    (releases / "TEMPLATE.md").write_text(TEMPLATE, encoding="utf-8")
    (releases / "1.2.2.md").write_text(HISTORICAL_NOTES, encoding="utf-8")
    (pending / "example-context.md").write_text(PENDING_NOTES, encoding="utf-8")
    return tmp_path


def test_repository_release_contract_is_unassigned_and_valid():
    release = validate_release(Path(__file__).resolve().parents[3])
    assert release.version == "unassigned"
    assert release.tag is None
    assert release.notes_path is None


def test_production_tag_selects_pending_record_and_renders_version(tmp_path):
    repository_root = _release_repository(tmp_path)
    release = validate_release(
        repository_root,
        "prod-v1.2.3",
        "docs/releases/pending/example-context.md",
    )
    rendered = tmp_path / "rendered.md"
    render_release_notes(release, rendered)

    assert release.version == "1.2.3"
    assert release.tag == "prod-v1.2.3"
    assert release.notes_path.name == "example-context.md"
    assert rendered.read_text(encoding="utf-8").startswith(
        "# Salt All The Things 1.2.3\n"
    )


@pytest.mark.parametrize("tag", ("v1.2.3", "prod-v01.2.3", "prod-v1.2"))
def test_malformed_production_tag_fails(tmp_path, tag):
    repository_root = _release_repository(tmp_path)
    with pytest.raises(ReleaseValidationError, match="production tag"):
        validate_release(
            repository_root,
            tag,
            "docs/releases/pending/example-context.md",
        )


@pytest.mark.parametrize(
    "path",
    (
        "docs/releases/1.2.2.md",
        "docs/releases/pending/../example-context.md",
        "/tmp/example-context.md",
    ),
)
def test_selected_record_must_be_safe_pending_path(tmp_path, path):
    repository_root = _release_repository(tmp_path)
    with pytest.raises(ReleaseValidationError, match="release record"):
        validate_release(repository_root, "prod-v1.2.3", path)


def test_source_version_must_remain_unassigned(tmp_path):
    repository_root = _release_repository(tmp_path)
    (repository_root / "VERSION").write_text("1.2.3\n", encoding="utf-8")
    with pytest.raises(ReleaseValidationError, match="must remain 'unassigned'"):
        validate_release(repository_root)


def test_missing_required_section_fails(tmp_path):
    repository_root = _release_repository(tmp_path)
    notes = repository_root / "docs/releases/pending/example-context.md"
    notes.write_text(
        notes.read_text(encoding="utf-8").replace(
            "## Rollback\n\n- Redeploy the previously validated tag.\n\n", ""
        ),
        encoding="utf-8",
    )
    with pytest.raises(ReleaseValidationError, match="Rollback"):
        validate_release(repository_root)


@pytest.mark.parametrize(
    "unsafe_text",
    (
        "TODO",
        "postgresql://release-user:not-safe@example.invalid/release",
        "client_secret=not-safe",
        "-----BEGIN PRIVATE KEY-----",
    ),
)
def test_placeholder_or_secret_bearing_pending_notes_fail(tmp_path, unsafe_text):
    repository_root = _release_repository(tmp_path)
    notes = repository_root / "docs/releases/pending/example-context.md"
    notes.write_text(
        notes.read_text(encoding="utf-8").replace(
            "A concrete release outcome.", unsafe_text
        ),
        encoding="utf-8",
    )
    with pytest.raises(ReleaseValidationError):
        validate_release(repository_root)
