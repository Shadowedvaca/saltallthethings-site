# Testing and Validation Standard

This document is authoritative for test-layer selection, regression evidence,
coverage ratchets, browser automation, flaky-test handling, and validation
exceptions. `reference/development-and-release.md` owns promotion gates and
environment roles. `reference/testing-profile.md` contains SATT's exact tools,
commands, baselines, and evidence locations.

## Required test layers

Every implementation child must use the narrowest layers that prove its
acceptance criteria and the complete applicable cumulative validation before
handoff. A changed behavior needs coverage at the lowest useful layer and at
each boundary where a realistic failure would otherwise escape:

- pure Python or JavaScript unit/contract tests for isolated decisions;
- API/service and serializer tests for backend contracts;
- isolated database tests and fresh migration validation for persistence;
- static browser contracts for markup, script syntax, accessibility hooks, and
  deterministic frontend logic;
- automated browser tests for rendering, navigation, authentication boundaries,
  and critical user journeys; and
- container/runtime checks for packaging, startup, migration, health metadata,
  recovery, or deployment changes.

Documentation-only work uses documentation, link, release-contract, and
process-contract checks. It does not manufacture application deployment or
manual UI evidence.

## Regression and cumulative evidence

A defect fixed under a parent receives an automated regression test that fails
for the defect and passes for the correction. If automation is genuinely
impossible, the child must record an explicit exception with the reason,
bounded manual evidence, risk, owner, and follow-up issue. Convenience or time
pressure is not an exception.

Parent-cadence work validates both the active child and the cumulative branch.
Later children must preserve earlier regression evidence. Automated browser
evidence is technical completion evidence; it does not substitute for a human
UI approval required by the selected User Validation Timing.

## Coverage ratchets

Coverage is a change detector, not a quality score. CI enforces the checked-in
overall Python baseline and changed executable-line baseline defined in the
testing profile. A child may raise either baseline after measuring the complete
safe suite. It must not lower, exclude, or bypass a baseline merely to make a
change pass. Generated code, migrations, tests, and explicit entry-point glue
may be excluded only by the canonical configuration and must be validated by
their purpose-built layers.

Changed-line coverage applies to executable Python application lines changed
from the pull request base. A change with uncovered executable lines must add
tests or document an approved exception; an empty application diff is reported
as not applicable, not as synthetic 100% evidence.

## Isolation and deterministic data

Database tests require an explicit isolated `TEST_DATABASE_URL` and must fail
closed rather than fall back to any runtime or production database. Tests must
not print connection values. AI providers, OAuth, Google Drive, email, and
other external services are mocked unless an authorized environment smoke test
explicitly requires the environment-specific integration. Test identities and
fixtures are deterministic, synthetic, bounded, and cleaned up where they
persist.

Browser automation runs against local test content or an explicitly approved
isolated environment. It must block unexpected external requests, use no real
credentials or Drive resources, and retain failure artifacts without capturing
secret-bearing configuration.

## Failure artifacts and flaky tests

CI retains bounded logs, screenshots, video, traces, and coverage reports only
where they help diagnose failures. Artifacts must not contain secrets, database
URLs, private rows, tokens, or expanded environment configuration.

Tests do not receive blind automatic retries. One diagnostic rerun may be
performed after preserving the first failure, and both outcomes are recorded.
A known flaky test needs an issue, owner, reason, expiry/review date, and a
non-flaky replacement signal. Quarantine cannot suppress security, migration,
coverage, critical-journey, or promotion checks.

## Emergency exceptions

An emergency correction does not silently inherit permission to skip tests or
promotion gates. Any proposed exception must be explicitly approved for the
exact commit and record: incident/risk, omitted evidence, minimum evidence that
still passed, environment and data boundaries, rollback, approver, expiry, and
a reconciliation issue. Normal production still requires successful isolated
test deployment for the exact production SHA. Changing that invariant requires
a separately approved workflow change; prose or a hotfix branch cannot bypass
it.
