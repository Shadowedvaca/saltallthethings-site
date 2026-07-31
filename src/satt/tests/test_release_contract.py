"""Release metadata validation and publication contract tests."""

from pathlib import Path

import pytest

from scripts.validate_release import ReleaseValidationError, validate_release


REQUIRED_NOTES = """# Salt All The Things {version}

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

TEMPLATE = """# Salt All The Things X.Y.Z

## Highlights

## Fixes/Changes

## Validation

## Deployment/Migrations

## Rollback

## Known Limitations
"""


def _release_repository(tmp_path: Path, version: str = "1.2.3") -> Path:
    releases = tmp_path / "docs" / "releases"
    releases.mkdir(parents=True)
    (tmp_path / "VERSION").write_text(f"{version}\n", encoding="utf-8")
    (releases / "TEMPLATE.md").write_text(TEMPLATE, encoding="utf-8")
    (releases / f"{version}.md").write_text(
        REQUIRED_NOTES.format(version=version),
        encoding="utf-8",
    )
    return tmp_path


def test_repository_release_contract_is_valid():
    repository_root = Path(__file__).resolve().parents[3]

    release = validate_release(repository_root)

    assert release.version == "0.0.4"
    assert release.tag == "prod-v0.0.4"
    assert release.notes_path.name == "0.0.4.md"


def test_matching_production_tag_is_valid(tmp_path):
    repository_root = _release_repository(tmp_path)

    release = validate_release(repository_root, "prod-v1.2.3")

    assert release.tag == "prod-v1.2.3"


@pytest.mark.parametrize(
    ("version", "tag"),
    (
        ("1.2.3", "v1.2.3"),
        ("1.2.3", "prod-v1.2.4"),
        ("01.2.3", "prod-v01.2.3"),
    ),
)
def test_malformed_or_mismatched_version_tag_fails(tmp_path, version, tag):
    repository_root = _release_repository(tmp_path, version)

    with pytest.raises(ReleaseValidationError):
        validate_release(repository_root, tag)


def test_mismatched_release_heading_fails(tmp_path):
    repository_root = _release_repository(tmp_path)
    notes = repository_root / "docs" / "releases" / "1.2.3.md"
    notes.write_text(
        notes.read_text(encoding="utf-8").replace(
            "# Salt All The Things 1.2.3",
            "# Salt All The Things 1.2.4",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReleaseValidationError, match="first heading"):
        validate_release(repository_root)


def test_missing_required_section_fails(tmp_path):
    repository_root = _release_repository(tmp_path)
    notes = repository_root / "docs" / "releases" / "1.2.3.md"
    notes.write_text(
        notes.read_text(encoding="utf-8").replace(
            "## Rollback\n\n- Redeploy the previously validated tag.\n\n",
            "",
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
def test_placeholder_or_secret_bearing_notes_fail(tmp_path, unsafe_text):
    repository_root = _release_repository(tmp_path)
    notes = repository_root / "docs" / "releases" / "1.2.3.md"
    notes.write_text(
        notes.read_text(encoding="utf-8").replace(
            "A concrete release outcome.",
            unsafe_text,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReleaseValidationError):
        validate_release(repository_root)
