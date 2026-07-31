"""Authoritative application version."""

import re
from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"
APP_VERSION = _VERSION_FILE.read_text(encoding="utf-8").strip()

if not re.fullmatch(r"\d+\.\d+\.\d+", APP_VERSION):
    raise RuntimeError(f"Invalid semantic version in {_VERSION_FILE.name}")
