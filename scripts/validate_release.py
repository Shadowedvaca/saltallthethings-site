"""Validate historical and pending release records and production selections."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re


SEMVER_TEXT = r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
SEMVER_PATTERN = re.compile(SEMVER_TEXT)
TAG_PATTERN = re.compile(rf"prod-v(?P<version>{SEMVER_TEXT})")
PENDING_NAME_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.md")
PENDING_HEADING = "# Salt All The Things — Pending Release"
REQUIRED_SECTIONS = (
    "Highlights",
    "Fixes/Changes",
    "Validation",
    "Deployment/Migrations",
    "Rollback",
    "Known Limitations",
)
PLACEHOLDER_PATTERNS = (
    re.compile(r"\b(?:TODO|TBD|FIXME|PLACEHOLDER)\b", re.IGNORECASE),
    re.compile(r"\bX\.Y\.Z\b", re.IGNORECASE),
)
TEMPLATE_SENTENCES = (
    "Summarize the most important user-visible or operational outcomes.",
    "List shipped behavior and intentional changes.",
    "Record automated, migration, deployment, and manual validation evidence.",
    "Describe deployment requirements and database or data-contract impact.",
    "Describe the tested or actionable recovery path.",
    "Record accepted limitations and focused follow-up work.",
)
SECRET_PATTERNS = (
    ("private key material", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE)),
    ("credential-bearing URL", re.compile(r"\b(?:https?|ssh)://[^/\s:@]+:[^/\s@]+@", re.IGNORECASE)),
    ("database URL", re.compile(r"\b(?:postgres(?:ql)?(?:\+asyncpg)?|mysql|mariadb|mongodb|redis)://", re.IGNORECASE)),
    ("access token", re.compile(r"\b(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})\b")),
    ("assigned credential value", re.compile(r"(?im)^\s*(?:[-*]\s*)?(?:`)?(?:password|secret|token|api[_-]?key|client[_-]?secret|database_url)(?:`)?\s*[:=]\s*[^\s`]+")),
)


class ReleaseValidationError(ValueError):
    """Raised when release metadata is unsafe or internally inconsistent."""


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag: str | None
    notes_path: Path | None


def _section_body(content: str, section: str) -> str:
    match = re.search(
        rf"(?ms)^## {re.escape(section)}\s*$\n(?P<body>.*?)(?=^## |\Z)", content
    )
    return match.group("body").strip() if match else ""


def _validate_document(notes_path: Path, expected_heading: str) -> list[str]:
    errors: list[str] = []
    content = notes_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    if not lines or lines[0] != expected_heading:
        errors.append(f"{notes_path.name}: first heading must be '{expected_heading}'")

    positions: list[int] = []
    for section in REQUIRED_SECTIONS:
        heading = f"## {section}"
        count = content.count(heading)
        if count != 1:
            errors.append(f"{notes_path.name}: expected exactly one '{heading}', found {count}")
            continue
        positions.append(content.index(heading))
        if not _section_body(content, section):
            errors.append(f"{notes_path.name}: '{heading}' must not be empty")
    if len(positions) == len(REQUIRED_SECTIONS) and positions != sorted(positions):
        errors.append(f"{notes_path.name}: required sections must remain in template order")

    for pattern in PLACEHOLDER_PATTERNS:
        if pattern.search(content):
            errors.append(f"{notes_path.name}: placeholder text matched {pattern.pattern!r}")
    for sentence in TEMPLATE_SENTENCES:
        if sentence in content:
            errors.append(f"{notes_path.name}: replace template sentence {sentence!r}")
    for description, pattern in SECRET_PATTERNS:
        if pattern.search(content):
            errors.append(f"{notes_path.name}: prohibited {description} detected")
    return errors


def _validate_template(template_path: Path) -> list[str]:
    if not template_path.is_file():
        return [f"missing release-note template: {template_path.as_posix()}"]
    content = template_path.read_text(encoding="utf-8")
    errors: list[str] = []
    if not content.startswith(f"{PENDING_HEADING}\n"):
        errors.append("release-note template must use the pending-release heading")
    for section in REQUIRED_SECTIONS:
        if content.count(f"## {section}") != 1:
            errors.append(f"release-note template must contain exactly one '## {section}'")
    return errors


def _pending_path(root: Path, supplied: str) -> Path:
    relative = Path(supplied)
    if relative.is_absolute() or not PENDING_NAME_PATTERN.fullmatch(relative.name):
        raise ReleaseValidationError("release record must be a lowercase hyphenated Markdown filename")
    expected_parent = Path("docs/releases/pending")
    if relative.parent != expected_parent:
        raise ReleaseValidationError("release record must be directly under docs/releases/pending/")
    resolved = (root / relative).resolve()
    pending_root = (root / expected_parent).resolve()
    if resolved.parent != pending_root or not resolved.is_file():
        raise ReleaseValidationError(f"pending release record not found: {supplied}")
    return resolved


def validate_release(
    repository_root: Path,
    tag: str | None = None,
    notes_path: str | None = None,
) -> ReleaseInfo:
    """Validate repository records and, when supplied, a production selection."""

    root = repository_root.resolve()
    releases_path = root / "docs" / "releases"
    errors = _validate_template(releases_path / "TEMPLATE.md")

    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if version != "unassigned":
        errors.append("VERSION must remain 'unassigned'; production version comes from the tag")

    historical = sorted(path for path in releases_path.glob("*.md") if path.name != "TEMPLATE.md")
    if not historical:
        errors.append("no historical curated release notes found")
    for path in historical:
        if not SEMVER_PATTERN.fullmatch(path.stem):
            errors.append(f"{path.name}: historical filename must be canonical X.Y.Z")
            continue
        errors.extend(_validate_document(path, f"# Salt All The Things {path.stem}"))

    pending = sorted((releases_path / "pending").glob("*.md"))
    for path in pending:
        if not PENDING_NAME_PATTERN.fullmatch(path.name):
            errors.append(f"{path.name}: pending filename must be lowercase and hyphenated")
        errors.extend(_validate_document(path, PENDING_HEADING))

    if (tag is None) != (notes_path is None):
        errors.append("production validation requires both tag and pending release record")

    selected: Path | None = None
    selected_tag: str | None = None
    if tag is not None and notes_path is not None:
        match = TAG_PATTERN.fullmatch(tag)
        if not match:
            errors.append("production tag must be canonical prod-vX.Y.Z")
            selected_version = "invalid"
        else:
            selected_version = match.group("version")
            selected_tag = tag
        try:
            selected = _pending_path(root, notes_path)
        except ReleaseValidationError as error:
            errors.append(str(error))
    else:
        selected_version = "unassigned"

    if errors:
        raise ReleaseValidationError("\n".join(f"- {error}" for error in errors))
    return ReleaseInfo(selected_version, selected_tag, selected)


def render_release_notes(release: ReleaseInfo, destination: Path) -> None:
    if release.notes_path is None or release.tag is None:
        raise ReleaseValidationError("rendering requires a validated production selection")
    content = release.notes_path.read_text(encoding="utf-8")
    _, separator, body = content.partition("\n")
    if not separator:
        raise ReleaseValidationError("pending release record has no body")
    destination.write_text(f"# Salt All The Things {release.version}\n{body}", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--tag")
    parser.add_argument("--notes-path")
    parser.add_argument("--rendered-notes", type=Path)
    parser.add_argument("--github-output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        release = validate_release(args.repository_root, args.tag, args.notes_path)
        if args.rendered_notes:
            render_release_notes(release, args.rendered_notes)
    except (OSError, ReleaseValidationError) as error:
        raise SystemExit(f"Release validation failed:\n{error}") from error

    print(f"Release contract valid: version={release.version} tag={release.tag or 'unassigned'}")
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"version={release.version}\n")
            output.write(f"tag={release.tag or ''}\n")
            output.write(
                "notes_path="
                + (release.notes_path.relative_to(args.repository_root.resolve()).as_posix() if release.notes_path else "")
                + "\n"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
