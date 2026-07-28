# Delivery and Release Governance

This is the canonical delivery contract for Salt All The Things. `AGENTS.md`,
`CLAUDE.md`, repository workflows, and release documentation must remain
consistent with it.

## Release environments and gates

| Environment | Source | Trigger | Authorization |
|---|---|---|---|
| Development | Shared `codex/<parent-issue-title-slug>` branch commit | Manual `deploy-dev.yml` dispatch with an explicit branch | Child implementation may deploy only after local validation |
| Test | Approved commit on `main` | `deploy-test.yml` after the cumulative pull request is explicitly approved and merged | Child approval does not authorize merge or test deployment |
| Production | Exact tested `main` commit tagged `prod-vX.Y.Z` | Tag-gated production workflow | Requires separate, explicit production-release approval |

Production never deploys from an ordinary branch push or merge. Tags are
immutable and must not be reused or force-pushed. Static frontend and FastAPI
backend artifacts must come from the same commit.

The repository is currently transitioning to this contract under milestone
`Cleanup & DevOps Foundation`. Until issue #14 completes, the legacy direct
production workflow is an acknowledged risk, not an authorized release path.

## Foundation branch and approval contract

- Parent issue #3 owns release `0.0.1`.
- The ordered child issues are #4 through #15.
- Work uses one branch,
  `codex/establish-cleanup-environment-isolation-and-release-engineering`, based
  on an up-to-date `main`.
- Work uses one cumulative draft pull request.
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

## Version and release record

`VERSION` is the authoritative semantic version. Release notes live at
`docs/releases/X.Y.Z.md` and must use the matching
`# Salt All The Things X.Y.Z` heading. The running application, validation
tools, production tag, and GitHub Release must report the same version and
commit.
