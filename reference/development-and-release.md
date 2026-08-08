# Development and Release Standard

This document is authoritative for quality gates, environment roles,
deployments and promotions, version authority, cumulative release notes,
database and secret safety, rollback, and release evidence.
`reference/work-management.md` owns issues, delivery slices, external run
inputs, approvals, and closure. `docs/delivery.md` is the human-facing system
description; linked runbooks contain exact operator mechanics.

## Development loop and quality gates

1. Read the parent, selected ordered children, both external run inputs, and
   relevant repository references before changing implementation.
2. Work on the branch and pull request defined by Integration Cadence. Move
   only the active child to `In progress`.
3. Implement the selected scope and maintain its tests, documentation, and
   cumulative release note. Do not change `VERSION` without Mike's exact
   selection.
4. Run focused checks while iterating, then the complete applicable local and
   CI-equivalent validation. For application changes this includes release
   validation, Python compilation/tests, migration checks, JavaScript syntax
   and browser-contract tests, and container checks where supported.
5. Push the tested commit and, when the child needs an integrated artifact,
   deploy the exact approved branch commit to isolated development through
   `deploy-dev.yml`.
6. Reconcile the entire cumulative diff and record the AI-executable technical
   evidence. State whether manual human UI validation is applicable and when it
   will be due, but do not perform it yet.
7. Stop at the Child development complete gate. Continue only after the child
   receives the required approval.
8. After approval, perform manual human UI validation only when User Validation
   Timing makes it due: `Child` after each applicable child approval, `Parent`
   after every selected child approval, or `Release` after test promotion. A
   failed manual check returns the affected scope to implementation and renewed
   technical completion before promotion.

Documentation-only changes do not manufacture application, deployment, or
manual UI checks. Run documentation/link checks, release validation, and every
repository quality check relevant to the process-supporting files changed.

The CI implementation is `.github/workflows/pull-request-validation.yml`.
Local commands and the precise validation matrix live in `docs/delivery.md`,
`scripts/ci_validation.py`, and the workflow itself.

## Environment roles and promotion

| Environment | Source and trigger | Role |
|---|---|---|
| Development | Explicit `codex/*` branch manually dispatched to `deploy-dev.yml` | Isolated branch artifact and pre-integration validation. |
| Test | Exact commit pushed to `main`, which triggers `deploy-test.yml` | Integration and release-candidate evidence. |
| Production | Exact tested `main` commit tagged `prod-vX.Y.Z`, which triggers `deploy-prod.yml` | Live immutable release; successful verification then publishes the GitHub Release. |

Frontend and backend always promote from the same commit. Development, test,
and production use separate runtime identity, configuration, database storage,
credentials, and GitHub environments.
Ordinary branch pushes and merges cannot deploy production.

For Parent Integration Cadence, merge/test promotion occurs once for the
cumulative selected slice. For Child cadence, each child has its own
merge/test promotion and Mike-selected version. Follow User Validation Timing
independently. Child- and Parent-timed validation use prepared development
artifacts after the required child approvals and before their applicable test
promotion. Release-timed validation uses the immutable test candidate after
test promotion and before production.

At the Promotion to test gate, one approval authorizes the ready PR merge and
the resulting automatic test deployment. At the Promotion to production gate,
one approval authorizes creation of the exact selected tag and the resulting
production workflow. Do not split either into extra approval prompts.

Exact environment inventory and operator procedures:

- `docs/development-environment.md` — development bootstrap, isolation,
  validation, backup, and recovery;
- `docs/test-environment.md` — test bootstrap, isolation, validation, reset,
  backup, and recovery;
- `docs/production-cutover.md` — production preflight, migration, backup,
  continuity verification, cutover, rollback, and observation window; and
- `reference/git-cicd-workflow.md` — operational Git and CI/CD commands.

## Mike-only version authority

Mike is the sole authority for selecting the exact version. AI must never
invent, infer, calculate, increment, or replace a version based on GitHub state,
issue wording, existing tags, package metadata, semantic-version convention, or
any other signal. If an exact version has not been supplied, report that the
version-dependent step is pending; do not choose one.

After Mike supplies the exact version, AI may apply it to repository-defined
sources, verify consistency, and report mismatches. SATT's authoritative source
is `VERSION`. FastAPI metadata, health responses, validation, the release-note
filename and heading, the production tag, workflow metadata, and the GitHub
Release must agree with it. See `docs/versioning-and-releases.md` and
`scripts/validate_release.py`.

## Cumulative release notes

Release notes use `docs/releases/X.Y.Z.md` and the required structure in
`docs/releases/TEMPLATE.md`.

- Once Mike has selected the exact version, the first approved child in a
  delivery slice creates the matching note when absent or updates it when the
  slice is continuing an existing release.
- Every later child reconciles that same note against the actual cumulative
  diff and recorded evidence. Remove stale promises; do not describe intended
  behavior as shipped behavior.
- Before test promotion, reconcile the complete PR diff, checks, migrations,
  deployment impact, rollback, limitations, and user-visible changes.
- Before production promotion, reconcile the note again with exact test
  evidence and the selected tag. `python scripts/validate_release.py` must pass.
- Never put secrets, credentials, connection values, private operational data,
  template instructions, or placeholders in release notes.

## Database, migrations, secrets, and backups

These safeguards apply throughout implementation and release:

- Use only the database assigned to the active environment. Tests require an
  explicit isolated test database and must refuse production configuration.
- Review every Alembic migration, validate upgrade to all heads on fresh and
  applicable existing data, and exercise the repository-supported recovery
  path. Do not silently downgrade or rewrite applied production migrations.
- Keep production PostgreSQL private and preserve the SATT-only isolation
  boundaries implemented by Compose, named volumes, schemas, and workflows.
- Never print expanded Compose configuration or emit API keys, tokens,
  passwords, private keys, OAuth secrets, database URLs, rows, or complete
  secret-bearing records. Verify only configured presence or one-way
  fingerprints where the repository supports them.
- Use environment-specific secrets and external-service resources. An explicit
  non-production opt-in never authorizes production credentials or data.
- Create and verify the repository-defined bounded backup before a migration or
  release step that requires one. Preserve release dumps and rollback sources
  for their documented windows.
- Restoring a database, deleting a volume, retiring a rollback source, or
  otherwise destroying data requires approval against the exact target and
  state. Automatic rollback is limited to the safe application/runtime actions
  implemented by the production workflow.

`docs/development-environment.md`, `docs/test-environment.md`, and
`docs/production-cutover.md` are the exact mechanics. Do not substitute a
generic database or recovery procedure.

## Integration, production, and rollback

After all children in the applicable slice are approved and required pre-test
human validation has passed, reconcile the cumulative PR and request Promotion
to test approval. Merge through the PR; the resulting `main` push deploys that
exact commit to test. Record workflow, migration, health, integration, and any
required manual UI evidence.

Production remains blocked unless the exact candidate commit has a completed,
successful `deploy-test.yml` push run for `main`. `deploy-prod.yml` queries the
GitHub Actions API and fails closed unless that run's `head_sha` exactly equals
the production tag commit. Main ancestry alone is insufficient.

After exact-SHA test evidence, release reconciliation, and Release-timed
validation are complete, request Promotion to production approval. Create only
the exact Mike-selected `prod-vX.Y.Z` tag on the exact tested `main` commit. The
tag is immutable: never move, reuse, delete/recreate, or force-push it. The
production workflow validates the version, tag, notes, target, main ancestry,
exact-SHA test-promotion success, backups, migrations, continuity, and health
before the least-privilege publisher creates or updates the matching GitHub
Release.

Hotfixes retain the same evidence and authority model. Any shortened test path
requires an explicit material-risk decision, recorded rationale, and later
reconciliation. Mike still selects the exact version.

Rollback follows the environment-specific runbook. Prefer a compatible,
previously validated application artifact. Database restore, migration
downgrade, destructive cleanup, infrastructure, DNS, GitHub environment, and
secret changes require authority for the exact action unless already covered by
an approved gate and implemented workflow.

## Release evidence

For each promotion, record the applicable:

- selected version, tag, commit, branch, and pull request;
- local and CI validation results;
- development/test/production workflow run and environment health metadata;
- migration heads, backup verification, and continuity evidence;
- manual human UI checklist/results or `not applicable` rationale;
- cumulative release-note reconciliation;
- rollback readiness, limitations, deviations, and follow-up work; and
- GitHub Release result after successful production verification.
