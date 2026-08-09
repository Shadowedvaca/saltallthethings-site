# SATT Testing Profile

This profile implements `reference/testing-and-validation.md` for this
repository. Run commands from the repository root.

## Toolchain and commands

| Layer | Canonical command | Required when |
|---|---|---|
| Release/docs | `python scripts/validate_release.py` and `python scripts/validate_repository_docs.py` | Every child; include link/process checks when documentation or workflows change. |
| Python compile | `python -m compileall -q src/satt scripts` | Python changes. |
| Focused Python | `python -m pytest <focused paths> -q` | While iterating. |
| Full Python, migrations, coverage | `python scripts/ci_validation.py` | Pull-request equivalent in GitHub Actions with its loopback isolated PostgreSQL service. |
| JavaScript syntax | `node --check <changed file>`; CI checks every `js/*.js` | JavaScript changes and cumulative PR validation. |
| Static browser contracts | `node scripts/test_frontend_contract.js` and `node scripts/test_guest_bank_frontend.js` | Frontend or shared data-contract changes and cumulative validation. |
| Automated browser | `npm ci`, `npx playwright install chromium`, `npm run test:e2e` | Frontend behavior, auth/navigation boundaries, environment-facing UI configuration, and cumulative parent/release integration. |
| Container/runtime | The `container` job in `.github/workflows/pull-request-validation.yml` | Packaging, runtime, migration, recovery, workflow, or cumulative release validation. |

## Layer classification

| Layer | Current locations and evidence |
|---|---|
| Static | `compileall`, `node --check`, `scripts/validate_release.py`, `scripts/validate_repository_docs.py`, workflow YAML parsing, and the two `scripts/test_*frontend*.js` browser contracts. |
| Unit | Pure contract and helper tests in `src/satt/tests/`, plus Node assertions in `scripts/test_frontend_contract.js` and `scripts/test_guest_bank_frontend.js`. |
| Integration/database | API/service tests using `db_client`/`db_session`, Alembic upgrade/head checks, and the fresh PostgreSQL container job. |
| Provider boundary | `test_ai_*.py`, `test_gdrive.py`, and environment-contract tests with AI, OAuth, and Drive mocked or disabled. No ordinary PR test contacts a provider. |
| Regression | Focused tests named for the corrected behavior; every defect child under #47 adds one unless its issue records the approved exception required by the testing standard. |
| Automated UI/E2E | `tests/e2e/critical-journeys.spec.js` under the pinned Playwright runner, separate from human UI approval. |
| Deployed smoke | `satt.scripts.environment_smoke`, public `/api/health`, migration-head checks, and the bounded checks in the development, test, and production workflow/runbooks. |

## Gate mapping

- **Child development:** focused tests while iterating, followed by every
  applicable local/CI-equivalent layer, cumulative release-note reconciliation,
  and an exact development artifact when the child needs one. This evidence
  supports **Child development complete** approval.
- **PR integration:** `.github/workflows/pull-request-validation.yml` runs the
  full isolated database suite and coverage, static contracts, Playwright
  journeys, production-image inspection, migrations, backup restore, and
  recovery. Parent cadence accumulates all selected-child regressions.
- **Manual human UI validation:** runs only at the timing selected in
  `reference/work-management.md` and remains a distinct approval/evidence item;
  automated E2E never self-approves it.
- **Test promotion:** after **Promotion to test** approval, `deploy-test.yml`
  deploys the exact merged `main` SHA and runs isolated test smoke, health,
  migration, and environment-boundary checks from `docs/test-environment.md`.
- **Production-safe smoke:** after separately approved **Promotion to
  production**, `deploy-prod.yml` first proves the exact SHA's successful test
  deployment, then performs backup/migration/continuity/health checks from
  `docs/production-cutover.md`. No child or emergency prose grants this gate.

These are the four named happy-path approval types: **Child development
complete**, **Manual human UI validation**, **Promotion to test**, and
**Promotion to production**. Testing evidence supports them but does not
collapse or implicitly authorize them.

Local database-backed validation is authorized only when
`TEST_DATABASE_URL` is explicitly configured for a disposable isolated test
database. `scripts/ci_validation.py` is intentionally GitHub-Actions-only and
constructs its URL from constrained loopback fields without printing it.

## Coverage baselines

`coverage.toml` measures branch coverage for production Python under
`src/satt`. Migrations, tests, and operational entry-point scripts have
purpose-built migration, contract, and container checks and are excluded from
the percentage. CI writes `coverage.json` and runs:

```text
python scripts/coverage_gate.py --coverage coverage.json --base origin/main
```

The checked-in baselines are in `coverage-baseline.json`:

- `overall_percent`: minimum total line coverage from the complete isolated
  database suite;
- `changed_line_percent`: minimum coverage of changed executable application
  lines relative to the PR base.

Changing an application line that coverage.py reports as executable makes that
line part of the changed-line gate. Baselines may stay fixed or increase after
a complete measurement; lowering them requires an explicit approved exception
under the canonical testing standard and must not be used merely to pass CI.

## Automated browser journeys

Playwright runs Chromium against a loopback static server with zero retries.
Unexpected non-loopback network requests are aborted. The initial critical
journeys are:

1. public homepage subtitle/Explore separation and horizontal overflow across
   representative desktop, tablet, mobile, and enlarged-text viewports; and
2. unauthenticated access to Show Management redirects to the local login page
   without contacting an API, OAuth provider, database, or Drive.

Each later UI child extends the lowest useful contract and the applicable
critical browser journey. Failure-only screenshots, video, and traces are
stored under `test-results/`; CI retains them for seven days.

## Evidence record

Child and integration handoffs record exact commands, outcomes, applicable
coverage totals, migration head/recovery result, browser journeys, container
result, workflow run, exact commit, environment health metadata when deployed,
exceptions/limitations, and rollback impact. Automated browser results and
manual human UI results are listed separately.
