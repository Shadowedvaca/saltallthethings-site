"""Validate canonical repository instructions and local Markdown links."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "reference/ai-context.md",
    "reference/work-management.md",
    "reference/development-and-release.md",
    "reference/testing-and-validation.md",
    "reference/testing-profile.md",
)


def main() -> int:
    agents = (ROOT / "AGENTS.md").read_bytes()
    claude = (ROOT / "CLAUDE.md").read_bytes()
    if agents != claude:
        raise SystemExit("AGENTS.md and CLAUDE.md must be byte-for-byte identical")
    entry = agents.decode("utf-8")
    positions = [entry.find(f"`{path}`") for path in REQUIRED]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise SystemExit("repository entry point does not contain the canonical reading order")

    for relative in (*REQUIRED, "MEMORY.md"):
        if not (ROOT / relative).is_file():
            raise SystemExit(f"required repository context is missing: {relative}")

    files = [ROOT / "AGENTS.md", ROOT / "CLAUDE.md", ROOT / "MEMORY.md"]
    files.extend((ROOT / "reference").glob("*.md"))
    files.extend((ROOT / "docs").rglob("*.md"))
    link_pattern = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
    for document in files:
        text = document.read_text(encoding="utf-8")
        for target in link_pattern.findall(text):
            target = target.strip().split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            resolved = (document.parent / target).resolve()
            if not resolved.exists():
                relative = document.relative_to(ROOT)
                raise SystemExit(f"broken local Markdown link in {relative}: {target}")
    print("repository documentation contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
