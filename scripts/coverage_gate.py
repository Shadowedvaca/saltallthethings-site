"""Enforce overall and changed-line Python coverage without leaking config."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


APP_PREFIX = "src/satt/"
EXCLUDED_PREFIXES = ("src/satt/migrations/", "src/satt/tests/", "src/satt/scripts/")


def _diff(base: str) -> str:
    result = subprocess.run(
        ["git", "diff", "--unified=0", f"{base}...HEAD", "--", "src/satt/*.py", "src/satt/**/*.py"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _changed_lines(diff: str) -> dict[str, set[int]]:
    changed: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:].replace("\\", "/")
            if not current.startswith(APP_PREFIX) or current.startswith(EXCLUDED_PREFIXES):
                current = None
        elif current and line.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if not match:
                continue
            start = int(match.group(1))
            count = int(match.group(2) or "1")
            changed.setdefault(current, set()).update(range(start, start + count))
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage", default="coverage.json")
    parser.add_argument("--baseline", default="coverage-baseline.json")
    parser.add_argument("--base", default="origin/main")
    args = parser.parse_args()

    report = json.loads(Path(args.coverage).read_text(encoding="utf-8"))
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    overall = float(report["totals"]["percent_covered"])
    required_overall = float(baseline["overall_percent"])
    if overall + 1e-9 < required_overall:
        raise SystemExit(f"overall coverage {overall:.2f}% is below {required_overall:.2f}%")

    executable: dict[str, set[int]] = {}
    covered: dict[str, set[int]] = {}
    for raw_name, details in report["files"].items():
        name = raw_name.replace("\\", "/")
        executable[name] = set(details["executed_lines"]) | set(details["missing_lines"])
        covered[name] = set(details["executed_lines"])

    applicable: set[tuple[str, int]] = set()
    hit: set[tuple[str, int]] = set()
    for name, lines in _changed_lines(_diff(args.base)).items():
        for number in lines & executable.get(name, set()):
            applicable.add((name, number))
            if number in covered.get(name, set()):
                hit.add((name, number))

    if not applicable:
        print(f"coverage gate passed: overall {overall:.2f}%; changed application lines not applicable")
        return 0

    changed_percent = 100.0 * len(hit) / len(applicable)
    required_changed = float(baseline["changed_line_percent"])
    if changed_percent + 1e-9 < required_changed:
        missing = ", ".join(f"{name}:{line}" for name, line in sorted(applicable - hit))
        raise SystemExit(
            f"changed-line coverage {changed_percent:.2f}% is below {required_changed:.2f}%; "
            f"uncovered: {missing}"
        )
    print(f"coverage gate passed: overall {overall:.2f}%; changed lines {changed_percent:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
