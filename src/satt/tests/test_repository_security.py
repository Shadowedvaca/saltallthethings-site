"""Repository-level secret regression checks."""

import hashlib
import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
COMPROMISED_DATABASE_PASSWORD_SHA256_PREFIX = "ab908dfd31fd"
TEXT_SUFFIXES = {
    "",
    ".example",
    ".html",
    ".ini",
    ".js",
    ".md",
    ".py",
    ".txt",
    ".yaml",
    ".yml",
}
IGNORED_PARTS = {".git", ".pytest_cache", "__pycache__", "venv"}
DATABASE_PASSWORD_PATTERN = re.compile(
    r"postgresql(?:\+asyncpg)?://[^:\s/]+:(?P<password>[^@\s]+)@"
)


def _repository_text_files():
    for path in REPOSITORY_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if IGNORED_PARTS.intersection(path.parts):
            continue
        if "src" in path.parts and "sv_common" in path.parts:
            continue
        if path.suffix.lower() in TEXT_SUFFIXES:
            yield path


def test_compromised_database_credential_is_not_tracked():
    matches = []
    for path in _repository_text_files():
        content = path.read_text(encoding="utf-8", errors="ignore")
        for candidate in DATABASE_PASSWORD_PATTERN.finditer(content):
            fingerprint = hashlib.sha256(
                candidate.group("password").encode()
            ).hexdigest()
            if fingerprint.startswith(COMPROMISED_DATABASE_PASSWORD_SHA256_PREFIX):
                matches.append(path.relative_to(REPOSITORY_ROOT).as_posix())

    assert matches == []
