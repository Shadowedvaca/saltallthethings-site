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
   context-owned pending release record. Record `Version: Unassigned`; do not
   reserve or propose a production version.
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
7. Record the child development-complete checkpoint. Under Parent cadence,
   continue immediately to the next ordered child unless a documented stop
   condition or Child-timed manual UI gate applies.
8. Perform manual human UI validation only when User Validation Timing makes it
   due: `Child` after each applicable child checkpoint, `Parent` after every
   selected child is technically complete, or `Release` after test promotion.
   A failed manual check returns affected scope to implementation and renewed
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
| Development | Explicit `codex/*` branch manually dispatched to `deploy-dev.yml` | Isolated branch artifact reporting version `unassigned`. |
| Test | Exact commit pushed to `main`, which triggers `deploy-test.yml` | Immutable candidate evidence reporting version `unassigned`. |
| Production | Exact tested `main` commit tagged with Mike's late-bound `prod-vX.Y.Z` | Live release reporting the tag-derived version; successful verification publishes the selected pending release record. |

Frontend and backend always promote from the same commit. Development, test,
and production use separate runtime identity, configuration, database storage,
credentials, and GitHub environments.
Ordinary branch pushes and merges cannot deploy production.

For Parent Integration Cadence, merge/test promotion occurs once for the
cumulative selected slice and automatic child checkpoints do not interrupt the
ordered work. For Child cadence, each child has its own merge/test and
production promotion. Follow User Validation Timing independently. Child- and
Parent-timed validation use prepared development artifacts before their
applicable test promotion. Release-timed validation uses the immutable test
candidate after test promotion and before production.

At the Promotion to test gate, one approval authorizes the ready PR merge and
the resulting automatic test deployment. After test succeeds, one combined
production gate asks for Mike's exact new tag and authorization to create it and
run production. Do not split version selection, tag creation, deployment, and
bounded verification into extra approval prompts when the approved candidate
and evidence remain unchanged.

Exact environment inventory and operator procedures:

- `docs/development-environment.md` — development bootstrap, isolation,
  validation, backup, and recovery;
- `docs/test-environment.md` — test bootstrap, isolation, validation, reset,
  backup, and recovery;
- `docs/production-cutover.md` — production preflight, migration, backup,
  continuity verification, cutover, rollback, and observation window; and
- `reference/git-cicd-workflow.md` — operational Git and CI/CD commands.

## Late-bound Mike-only version authority

Every delivery context records `Version: Unassigned` through successful test
validation. The checked-in `VERSION` fallback and non-production deployments
likewise report `unassigned`; package or draft metadata is not production
authority.

Mike alone selects the exact production tag. AI must never invent, infer,
calculate, increment, recommend as an implied default, or substitute a version
based on repository state, issue wording, metadata, milestones, semantic-version
convention, or prior tags.

Production derives the runtime version from Mike's immutable `prod-vX.Y.Z` tag
without changing the tested commit. FastAPI metadata, health responses,
deployment verification, and the GitHub Release must report that tag-derived
version. See `docs/versioning-and-releases.md` and
`scripts/validate_release.py`.

## Context-owned pending release records

Each delivery context maintains one uniquely named Markdown record under
`docs/releases/pending/` using `docs/releases/TEMPLATE.md`. The filename uses a
stable context slug, not a guessed version. Concurrent contexts must not share a
pending record.

- Reconcile the record after every child against the actual cumulative diff and
  evidence. Remove stale promises and never describe intended behavior as
  shipped.
- Before test promotion, reconcile the complete PR diff, checks, migrations,
  deployment impact, rollback, limitations, and user-visible changes.
- Before the combined production gate, reconcile it with exact test evidence.
- The approved annotated production tag identifies the exact pending record with
  one `Release-Record: docs/releases/pending/<context>.md` trailer. The workflow
  validates and publishes that record under the tag-derived version.
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

After all children in the applicable slice are technically complete and required
pre-test human validation has passed, reconcile the cumulative PR and request
Promotion to test approval. Merge through the PR; the resulting `main` push
deploys that exact commit to test. Record workflow, migration, health,
integration, and any required manual UI evidence.

Production remains blocked unless the exact candidate commit has a completed,
successful `deploy-test.yml` push run for `main`. `deploy-prod.yml` queries the
GitHub Actions API and fails closed unless that run's `head_sha` exactly equals
the production tag commit. Main ancestry alone is insufficient.

After exact-SHA test evidence, pending-record reconciliation, and Release-timed
validation are complete, inspect deployed production identity, repository tags
and releases, candidate SHA and PR, test results, record identity, rollback, and
risks. Report them, then ask in one question what exact new production tag Mike
wants and whether he approves creating it and deploying now. Do not include a
proposed version.

An answer supplying the exact tag and clear approval authorizes validation that
the tag is new and well formed, creation and push of one annotated tag on the
exact tested `main` SHA with the approved `Release-Record` trailer, the resulting
production deployment, bounded verification, and GitHub Release publication.
The tag is immutable: never move, reuse, delete/recreate, or force-push it. Ask
again only if the tag, candidate SHA, release record, evidence, deployment
mechanism, or required mutation changes after approval.

The production workflow validates the tag-derived version, selected record,
target, main ancestry, exact-SHA test-promotion success, backups, migrations,
continuity, and health before the least-privilege publisher creates or updates
the matching GitHub Release.

Hotfixes retain the same evidence and authority model. They do not silently
authorize a test bypass. Any proposed emergency exception is governed by
`reference/testing-and-validation.md`: it requires approval for the exact
commit, bounded minimum evidence, rollback, expiry, and a reconciliation issue.
The exact-SHA isolated-test requirement for production remains fail closed
unless a separately approved workflow change explicitly changes that invariant.
Mike still selects the exact production tag.

Rollback follows the environment-specific runbook. Prefer a compatible,
previously validated application artifact. Database restore, migration
downgrade, destructive cleanup, infrastructure, DNS, GitHub environment, and
secret changes require authority for the exact action unless already covered by
an approved gate and implemented workflow.

## Release evidence

For each promotion, record the applicable:

- selected tag and tag-derived version, commit, branch, and pull request;
- local and CI validation results;
- development/test/production workflow run and environment health metadata;
- migration heads, backup verification, and continuity evidence;
- manual human UI checklist/results or `not applicable` rationale;
- cumulative pending-release-record reconciliation;
- rollback readiness, limitations, deviations, and follow-up work; and
- GitHub Release result after successful production verification.
