# Delivery and Release Governance

This is the human-facing delivery contract for Salt All The Things.
`reference/work-management.md` and `reference/development-and-release.md` are
the canonical AI process instructions. They define Integration Cadence, User
Validation Timing, approval gates, version authority, and release evidence;
this document describes SATT's implemented delivery system and must remain
consistent with them.

## Release environments and gates

| Environment | Source | Trigger | Authorization |
|---|---|---|---|
| Development | Selected `codex/<slice-slug>` branch commit | Manual `deploy-dev.yml` dispatch with an explicit branch | Routine technical work within the selected scope |
| Test | Approved exact commit on `main` | `deploy-test.yml` after the applicable PR is merged | Single Promotion to test gate |
| Production | Exact tested `main` commit tagged `prod-vX.Y.Z` | Tag-gated production workflow | Single Promotion to production gate for Mike's exact selected tag |

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
the exact `VERSION` value, and the exact resolved commit. One-time server, DNS,
TLS, GitHub environment, and secret provisioning requires explicit
authorization. The detailed bootstrap, validation, cleanup, and rollback
procedure is in `docs/development-environment.md`.

## Isolated test implementation

SATT test uses `/opt/satt-platform` on `my-web-apps-test`, loopback port `8300`,
Compose project `satt-test`, and database volume `satt-test-postgres`.
`deploy-test.yml` runs only for a pushed commit on `main`, verifies
`github.sha`, and deploys that exact commit after the cumulative pull request
or Child-cadence pull request passes the single Promotion to test gate.

The deployment performs a bounded pre-deploy backup, runs migrations, verifies
local and public environment/version/commit metadata, verifies the final
Alembic revision, and runs an ephemeral authentication/integration smoke test
that removes its temporary identity. Test OAuth values are empty and
non-production external-service opt-in is false. The detailed bootstrap,
validation, reset, cleanup, and rollback procedure is in
`docs/test-environment.md`.

The registered `deploy.yml` entry point is manual development-only; it has no
branch-push trigger and no production job. Production deployment is isolated in
tag-only `deploy-prod.yml` and remains unauthorized until the canonical
production-promotion gate is approved.

## Production cutover implementation

`deploy-prod.yml` runs only for `prod-v*`, validates the authoritative version,
curated notes, exact tag target, and `main` ancestry, then fails closed unless
GitHub Actions reports a completed successful `deploy-test.yml` push run on
`main` whose `head_sha` exactly matches the tag commit. Only then may the
protected `production` job configure SSH or deploy the frontend and backend
together from the same standalone production image.

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

## Work and approval authority

GitHub issues and the Solo Development project are the work-status source of
truth. Parent/child hierarchy, controlled child expansion, Integration Cadence,
User Validation Timing, shared delivery slices, routine-work authorization, and
the four happy-path approval gates are defined only in
`reference/work-management.md`. Historical Foundation issue and branch details
remain in their GitHub records and release notes rather than in the active
process contract.

The chronological gate sequence is: complete AI-executable child work, receive
Child development complete approval, then perform Child- or Parent-timed manual
UI validation on the prepared cumulative development artifact when due. After
all pre-test validation passes, Promotion to test creates the immutable test
candidate. Release-timed manual UI validation occurs on that candidate before
the final Promotion to production. Integration Cadence independently controls
whether Parent uses one cumulative PR/test promotion or each Child uses its own
releasable PR, promotion, and Mike-selected version.

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
- `production`: deployments only from validated `prod-v*` tags after the final
  Promotion to production approval and exact-SHA test-promotion proof.

Changing GitHub environments, protection rules, repository secrets, servers,
or DNS requires authority for the exact action under the exception rules in
`reference/work-management.md`.

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

Mike alone selects the exact version. AI may apply that supplied value and
verify consistency but must never invent, infer, calculate, increment, or
replace it. Cumulative note timing and reconciliation are defined in
`reference/development-and-release.md`.

`scripts/validate_release.py` enforces the version, tag, filename, heading,
required-section, placeholder, and credential-safety contract in pull-request
validation without publishing. An approved `prod-vX.Y.Z` tag invokes
`deploy-prod.yml`, which also proves exact-SHA test promotion before any
production connection. Only after production deployment and public verification
succeed does a separate least-privilege job call `publish-release.yml` to
publish the matching curated note. Version selection, hotfixes, and rollback
behavior are documented in `docs/versioning-and-releases.md`.
