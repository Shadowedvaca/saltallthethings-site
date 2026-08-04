# Delivery and Release Governance

This is the human-facing delivery contract for Salt All The Things.
`reference/work-management.md` and `reference/development-and-release.md` are
the canonical AI process instructions. This document, repository workflows, and
release documentation must remain consistent with them.

## Release environments and gates

| Environment | Source | Trigger | Authorization |
|---|---|---|---|
| Development | Shared `codex/<parent-issue-title-slug>` branch commit | Manual `deploy-dev.yml` dispatch with an explicit branch | Child implementation may deploy only after local validation |
| Test | Approved commit on `main` | `deploy-test.yml` after the cumulative pull request is explicitly approved and merged | Child approval does not authorize merge or test deployment |
| Production | Exact tested `main` commit tagged `prod-vX.Y.Z` | Tag-gated production workflow | Requires separate, explicit production-release approval |

Production never deploys from an ordinary branch push or merge. Tags are
immutable and must not be reused or force-pushed. Static frontend and FastAPI
backend artifacts must come from the same commit.

## Isolated development implementation

SATT development uses `/opt/satt-platform` on `my-web-apps-dev`, loopback port
`8300`, Compose project `satt-development`, and database volume
`satt-development-postgres`. Port `8200` is occupied by another application and
must not be reused.

`deploy-dev.yml` accepts an explicit `codex/*` branch, resolves it to an
immutable commit, and deploys that exact commit with strict SSH host-key
verification. The workflow may build, migrate, restart, inspect, back up, and
clean up only the SATT development Compose project and its bounded backup
directory. It may not prune shared Docker state or operate on test or
production.

The public and local health checks must both report environment `development`,
version `0.0.7`, and the exact resolved commit. One-time server, DNS, TLS,
GitHub environment, and secret provisioning requires explicit authorization.
The detailed bootstrap, validation, cleanup, and rollback procedure is in
`docs/development-environment.md`.

## Isolated test implementation

SATT test uses `/opt/satt-platform` on `my-web-apps-test`, loopback port `8300`,
Compose project `satt-test`, and database volume `satt-test-postgres`.
`deploy-test.yml` runs only for a pushed commit on `main`, verifies
`github.sha`, and deploys that exact commit after the cumulative pull request
receives separate merge approval.

The deployment performs a bounded pre-deploy backup, runs migrations, verifies
local and public environment/version/commit metadata, verifies the final
Alembic revision, and runs an ephemeral authentication/integration smoke test
that removes its temporary identity. Test OAuth values are empty and
non-production external-service opt-in is false. The detailed bootstrap,
validation, reset, cleanup, and rollback procedure is in
`docs/test-environment.md`.

The repository is implementing this contract under milestone
`Cleanup & DevOps Foundation`. The registered `deploy.yml` entry point is now
manual development-only; it has no branch-push trigger and no production job.
Production deployment is isolated in tag-only `deploy-prod.yml` and remains
unauthorized until the release-integration, test, and production approval gates
are complete.

## Production cutover implementation

`deploy-prod.yml` runs only for `prod-v*`, validates the authoritative version,
curated notes, exact tag target, and `main` ancestry, and uses the protected
GitHub `production` environment. It checks out the immutable tag and deploys the
frontend and backend together from the same standalone production image.

The production Compose definition contains a stable `satt-production-app` and
private `satt-production-database` pair. PostgreSQL uses the explicitly named
`satt-production-postgres` volume and publishes no host port. The first cutover
creates live and stopped-runtime SATT-schema backups, restores the final dump into
a fresh volume, compares one-way authentication/data fingerprints, and promotes
frontend files extracted from the same immutable image. A failure restores the
prior static files and systemd runtime against the unchanged host database while
retaining dumps and the failed volume. Diagnostics are bounded to SATT.

The first cutover keeps the existing SATT systemd runtime and reverse-proxy path
available for 24 hours. Database restore is deliberately not automatic because
it is destructive and requires separate approval against the exact failed
release. The complete preflight, cutover, verification, and recovery procedure
is in `docs/production-cutover.md`. No production tag or operation is authorized
by committing that procedure.

## Foundation branch and approval contract

- Parent issue #3 owns the unshipped 0.0.1 and failed, unpublished 0.0.2
  Foundation attempts plus corrective patch 0.0.3.
- The ordered original children are #4 through #15; discovery added approved
  children #31 for the isolated production database cutover and #33 for the
  production-only verification corrections.
- The completed original slice used
  `codex/establish-cleanup-environment-isolation-and-release-engineering`.
- Corrective child #31 used `codex/isolate-production-database-cutover` from
  current `main` and its own cumulative pull request.
- Corrective child #33 uses
  `codex/correct-production-cutover-verification-release-0-0-3` from current `main`.
- Each child is implemented, validated, committed, pushed, deployed to isolated
  development when that environment exists, and reviewed independently.
- Approval of one child authorizes work on only the next ordered child.
- Child approval does not authorize merging, test deployment, tagging,
  production deployment, server changes, DNS changes, GitHub environment
  changes, or secret changes.
- Failed manual validation remains in the current child until corrected and
  revalidated.

## Milestones and issue traceability

The repository has two roadmap milestones:

1. `Cleanup & DevOps Foundation` contains parent #3 and children #4–#15.
2. `New Podcast Features` is deferred until the Foundation milestone is
   complete.

Implementation starts from a milestone issue. A release parent provides shared
context and ordered child issues provide separate implementation scopes.
Pull-request descriptions, commits, release notes, and validation evidence link
back to the active child and cumulative parent.

## Standard GitHub names

Repository or environment configuration uses these names:

- `DEV_HOST`
- `TEST_HOST`
- `PROD_HOST`
- `DEPLOY_SSH_KEY`
- `DEV_SSH_KNOWN_HOSTS`
- `TEST_SSH_KNOWN_HOSTS`
- `PROD_SSH_KNOWN_HOSTS`

Secret values are never printed, committed, returned to browsers, or copied into
release notes. Verification is limited to name/presence, configured-status
booleans, or a one-way SHA-256 fingerprint. AI and OAuth credentials remain
server-side and non-production environments must not reuse production
credentials, databases, API origins, or Drive resources.

## Intended GitHub environment protections

- `development`: manual branch deployments; no production resources; branch
  policy restricted to approved Foundation or later feature branches.
- `test`: deployments only from the approved `main` integration commit.
- `production`: deployments only from validated `prod-v*` tags after explicit
  production-release approval.

Changing GitHub environments, protection rules, repository secrets, servers,
DNS, or production requires explicit authorization at the time of change.

## Canonical application origins

| Tier | Application origin | Runtime identifiers |
|---|---|---|
| Local | `http://localhost:8200` | `ENVIRONMENT=local`, `DATABASE_ENVIRONMENT=local` |
| Development | `https://dev.saltallthethings.com` | `ENVIRONMENT=development`, `DATABASE_ENVIRONMENT=development` |
| Test | `https://test.saltallthethings.com` | `ENVIRONMENT=test`, `DATABASE_ENVIRONMENT=test` |
| Production | `https://saltallthethings.com` | `ENVIRONMENT=production`, `DATABASE_ENVIRONMENT=production` |

`SITE_URL` and `CORS_ORIGINS` use the matching origin. Browser calls use
same-origin `/api` and `/public` paths, so an immutable frontend cannot silently
cross tiers. Application startup rejects mismatched environment/database
ownership and rejects the production web origin in non-production.

Non-production Google OAuth configuration is disabled by default. An authorized
external-service smoke test must deliberately set
`ALLOW_NONPRODUCTION_EXTERNAL_SERVICES=true` and must still use non-production
credentials and Drive resources. AI credentials remain server-side in the
environment's isolated database.

## Container and pull-request validation

`Dockerfile` is the shared runtime artifact. The entrypoint validates
environment/database ownership before it runs `alembic upgrade head`, then
starts FastAPI as an unprivileged user. Explicit copy boundaries and
`.dockerignore` prevent local configuration, repository metadata, workbooks,
backups, tests, and release documentation from entering the image.

Compose definitions keep local, development, test, and production database
storage under distinct project and volume names. Production contains one private
PostgreSQL service with no published port. The first cutover restores a verified
SATT-schema dump into its fresh named volume and preserves the unchanged host
database as the separately approved rollback source.

`pull-request-validation.yml` has read-only repository permission and two
non-deployment jobs:

1. migrate a fresh loopback-only CI database and run the complete safe suite;
2. build and inspect the production image, start it with a fresh isolated
   container database, rehearse a SATT-schema dump/restore with fingerprint
   comparison, and verify health environment/version/commit metadata.

CI constructs database connection strings only inside the runner process after
asserting the GitHub Actions context, loopback host, port, user, and allowed
database names. It ignores any production database configuration and uses no
external AI, OAuth, or Drive credentials.

## Version and release record

`VERSION` is the authoritative semantic version. Release notes live at
`docs/releases/X.Y.Z.md` and must use the matching
`# Salt All The Things X.Y.Z` heading. The running application, validation
tools, production tag, and GitHub Release must report the same version and
commit.

`scripts/validate_release.py` enforces the version, tag, filename, heading,
required-section, placeholder, and credential-safety contract in pull-request
validation without publishing. A separately approved `prod-vX.Y.Z` tag invokes
`deploy-prod.yml`. Only after its production deployment and public verification
job succeeds does a separate least-privilege job call `publish-release.yml` to
publish the matching curated note. Version increments, hotfixes, and rollback
behavior are documented in `docs/versioning-and-releases.md`.
