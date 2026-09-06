"""Runtime release identity.

Development and test candidates remain unassigned. Production supplies the
version derived from the approved immutable tag.
"""

import os
from pathlib import Path
import re


_VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"
APP_VERSION = os.environ.get("SATT_VERSION") or _VERSION_FILE.read_text(
    encoding="utf-8"
).strip()

if APP_VERSION != "unassigned" and not re.fullmatch(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", APP_VERSION
):
    raise RuntimeError("SATT_VERSION must be 'unassigned' or canonical X.Y.Z")
