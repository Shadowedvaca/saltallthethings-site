"""Regression contracts for repository testing governance introduced by #54."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]


def _words(text: str) -> str:
    return " ".join(text.split())


def _coverage_gate_module():
    path = ROOT / "scripts" / "coverage_gate.py"
    spec = importlib.util.spec_from_file_location("coverage_gate", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ai_entry_points_are_identical_and_require_testing_context():
    agents = (ROOT / "AGENTS.md").read_bytes()
    assert agents == (ROOT / "CLAUDE.md").read_bytes()
    text = agents.decode("utf-8")
    assert text.index("reference/development-and-release.md") < text.index(
        "reference/testing-and-validation.md"
    ) < text.index("reference/testing-profile.md")
    memory = _words((ROOT / "MEMORY.md").read_text(encoding="utf-8"))
    assert "never in a substitute clone or temporary project directory" in memory
    assert "Do not record active issue status" in memory
    assert "Never store secrets" in memory


def test_coverage_baselines_and_changed_line_parser_are_enforced():
    baseline = json.loads((ROOT / "coverage-baseline.json").read_text(encoding="utf-8"))
    assert baseline["overall_percent"] >= 63.06
    assert baseline["changed_line_percent"] >= 90.0
    gate = _coverage_gate_module()
    parsed = gate._changed_lines(
        "+++ b/src/satt/example.py\n@@ -3,0 +4,2 @@\n+one\n+two\n"
        "+++ b/src/satt/tests/test_example.py\n@@ -1,0 +1 @@\n+ignored\n"
    )
    assert parsed == {"src/satt/example.py": {4, 5}}


def test_pull_request_workflow_runs_isolated_coverage_and_browser_gates():
    workflow_text = (ROOT / ".github/workflows/pull-request-validation.yml").read_text(
        encoding="utf-8"
    )
    workflow = yaml.safe_load(workflow_text)
    application_steps = workflow["jobs"]["application"]["steps"]
    rendered = json.dumps(application_steps)
    assert "scripts/ci_validation.py" in rendered
    assert "scripts/validate_repository_docs.py" in rendered
    assert "npm ci" in rendered
    assert "playwright install --with-deps chromium" in rendered
    assert "npm run test:e2e" in rendered
    assert "retention-days" in rendered
    assert "retries: 0" in (ROOT / "playwright.config.js").read_text(encoding="utf-8")


def test_testing_policy_keeps_automation_and_human_approval_separate():
    policy = _words(
        (ROOT / "reference/testing-and-validation.md").read_text(encoding="utf-8")
    )
    profile = _words((ROOT / "reference/testing-profile.md").read_text(encoding="utf-8"))
    assert "does not substitute for a human UI approval" in policy
    assert "must not lower" in policy
    assert "Tests do not receive blind automatic retries" in policy
    assert "successful isolated test deployment for the exact production SHA" in policy
    assert "Unexpected non-loopback network requests are aborted" in profile
    assert "Automated browser results and manual human UI results are listed separately" in profile
    for layer in (
        "Static",
        "Unit",
        "Integration/database",
        "Provider boundary",
        "Regression",
        "Automated UI/E2E",
        "Deployed smoke",
    ):
        assert f"| {layer} |" in profile
    for gate in (
        "Child development complete",
        "Manual human UI validation",
        "Promotion to test",
        "Promotion to production",
    ):
        assert gate in profile
