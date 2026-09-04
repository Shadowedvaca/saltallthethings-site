# Git and CI/CD Operations — SATT

This document contains operational Git and environment detail only.
`reference/work-management.md` is authoritative for delivery slices, external
run inputs, pull requests, approvals, and closure.
`reference/development-and-release.md` is authoritative for quality,
promotion, versions, release notes, and rollback.

## Branches

| Pattern | Purpose |
|---|---|
| `codex/<slice-slug>` | Normal Parent- or Child-cadence delivery slice. |
| `hotfix/<focused-slug>` | Separately approved emergency correction branched from current `main`. |

Never commit directly to `main`. Parent Integration Cadence uses one cumulative
branch and pull request for all selected children; Child cadence uses one per
child. Do not create a PR per child under Parent cadence.

## Environment inventory

| Tier | Source | Host alias | Compose project | App port | Database volume |
|---|---|---|---|---|---|
| Development | Explicit `codex/*` branch | `my-web-apps-dev` | `satt-development` | `127.0.0.1:8300` | `satt-development-postgres` |
| Test | Exact pushed `main` commit | `my-web-apps-test` | `satt-test` | `127.0.0.1:8300` | `satt-test-postgres` |
| Production | Exact tested commit with validated `prod-v*` tag | Production host | `satt-production` | Internal app port behind Nginx | `satt-production-postgres` |

The shared non-production servers reserve port `8300` for SATT. Other
applications use their own ports and resources; never operate on them.

Required GitHub configuration names are:

- development: `DEV_HOST`, `DEPLOY_SSH_KEY`, `DEV_SSH_KNOWN_HOSTS`;
- test: `TEST_HOST`, `DEPLOY_SSH_KEY`, `TEST_SSH_KNOWN_HOSTS`; and
- production: `PROD_HOST`, `DEPLOY_SSH_KEY`, `PROD_SSH_KNOWN_HOSTS`.

Values remain in protected GitHub/server configuration and must not be printed.

## Normal operational sequence

Use the active slice slug and the exact version supplied by Mike. Approval
timing comes from `reference/work-management.md`; the commands below do not
grant authority by themselves.

```powershell
git switch main
git pull --ff-only
git switch -c codex/<slice-slug>

# Implement and run applicable validation.
git push -u origin codex/<slice-slug>
gh workflow run deploy-dev.yml -f branch=codex/<slice-slug>

# At the single approved test-promotion gate, merge the ready PR.
# The resulting push to main triggers deploy-test.yml.

# At the single approved production-promotion gate only:
git tag prod-vX.Y.Z <exact-tested-main-commit>
git push origin prod-vX.Y.Z
```

`deploy-dev.yml` resolves the explicit branch to an immutable commit before
deployment. `deploy-test.yml` accepts only the pushed `main` commit.
`deploy-prod.yml` accepts only a validated matching immutable tag, queries
GitHub Actions for a completed successful `deploy-test.yml` push run with the
same exact SHA on `main`, and fails before SSH if that proof is absent. It
publishes the curated GitHub Release only after production verification
succeeds.

## Hotfix operations

A hotfix branches from current `main`, contains only the emergency correction,
and uses the same evidence, approval, exact-version, tag, and reconciliation
rules as normal delivery. It has no implied test-bypass privilege. Any proposed
exception must follow `reference/testing-and-validation.md`, identify the exact
commit and omitted/minimum evidence, and receive explicit approval. The current
production workflow still requires successful isolated test deployment for the
exact SHA and cannot be bypassed by branch naming or prose.

```powershell
git switch main
git pull --ff-only
git switch -c hotfix/<focused-slug>
```

Follow the same development artifact, ready PR, test promotion, and production
promotion mechanics after that point. Mike selects the exact version; do not
derive a patch number from the branch type.

## Operational references

- `docs/development-environment.md` — development deployment and recovery.
- `docs/test-environment.md` — test deployment, smoke checks, reset, and
  recovery.
- `docs/production-cutover.md` — production preflight, backups, migration,
  continuity, rollback, and observation.
- `docs/versioning-and-releases.md` — applying Mike's exact version and
  validating notes/tag/release consistency.
- `.github/workflows/pull-request-validation.yml` — actual CI validation.

Tags are immutable. Never reuse or force-push a production tag. Never print
expanded Compose configuration or secret-bearing environment values.
