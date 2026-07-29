# Git & CI/CD Workflow — SATT Standard

This document provides operational environment and Git detail.
`reference/work-management.md` and `reference/development-and-release.md` are
authoritative for issue lifecycle, delivery slices, approval boundaries,
review, integration, and release authorization. `docs/delivery.md` is the
human-facing companion. If these documents conflict, the two canonical
references win.

---

## Philosophy

- **Branches are cheap. Direct commits to main are not.**
- Every environment has a gate. Dev is the sandbox. Test is the integration check. Prod is the contract.
- Hotfixes are legitimate — they need their own fast lane, not a different philosophy.
- main should always reflect what is in or about to go to test/prod. Keep it clean.

---

## Branch Types

| Prefix | Purpose | Version bump |
|--------|---------|-------------|
| `codex/<parent-issue-title-slug>` | Ordered parent/child delivery on one cumulative branch | Release target selected by the parent |
| `codex/<focused-fix-slug>` | Independent planned fix | PATCH (`x.y.Z`) |
| `hotfix/*` | Separately approved emergency production fix | PATCH (`x.y.Z`) |

---

## Environments

Three environments, three gates:

| Environment | Purpose | Deployed by |
|-------------|---------|-------------|
| **dev** | Fast feedback sandbox. Break things here. | Manual trigger from feature branch |
| **test** | Integration gate. Matches prod config. | Auto on push to `main` (i.e. merged PR) |
| **prod** | Live. Real users/data. | Validated `prod-v*` tag after explicit approval |

---

## Shared non-production server inventory

Development and test run on separate shared servers. The same application port
is reserved on both servers so environment definitions remain symmetric.

| Port | Application | Development | Test |
|---|---|---|---|
| `8100` | Pull All The Things | `dev.pullallthethings.com` | `test.pullallthethings.com` |
| `8200` | Shadowedvaca site | `dev.shadowedvaca.com` | `test.shadowedvaca.com` |
| `8300` | Salt All The Things | `dev.saltallthethings.com` | reserved for issue #12 |

SATT development uses:

- SSH alias `my-web-apps-dev`;
- repository path `/opt/satt-platform`;
- Compose project `satt-development`;
- loopback binding `127.0.0.1:8300`;
- database volume `satt-development-postgres`; and
- GitHub environment `development`.

The manual workflow requires the configured secret names `DEV_HOST`,
`DEPLOY_SSH_KEY`, and `DEV_SSH_KNOWN_HOSTS`. It resolves the explicit
`codex/*` branch to an immutable commit before SSH and deploys only that commit.
See `docs/development-environment.md` for bootstrap, isolation, backup, smoke,
cleanup, and rollback procedures.

---

## Normal Feature Flow

```
1. Branch from main
   git checkout main && git pull
   git checkout -b codex/parent-issue-title

2. Develop, iterate
   [write code, run tests]

3. Deploy to dev — verify it works
   git push origin codex/parent-issue-title
   gh workflow run deploy-dev.yml -f branch=codex/parent-issue-title
   [verify in dev environment]

4. Obtain explicit merge approval, merge to main → test auto-deploys
   git checkout main
   git merge codex/parent-issue-title --no-ff
   git push origin main
   [verify in test environment]

5. Verify test, obtain separate production-release approval, then tag
   git tag prod-vX.Y.Z && git push origin prod-vX.Y.Z
```

**Rules:**
- Keep the cumulative branch and draft pull request until every ordered child
  and release integration check is complete
- Don't skip dev verification just because the change feels small
- Child approval authorizes only the next child; it never authorizes merge,
  test deployment, a production tag, or production deployment

---

## Hotfix Flow (something is broken in prod RIGHT NOW)

Hotfixes follow the same branch discipline — no shortcuts on that — but they have a fast lane to prod that bypasses the normal test-first requirement.

```
1. Branch from main (not from a stale feature branch)
   git checkout main && git pull
   git checkout -b hotfix/describe-the-break

2. Make the MINIMAL fix — only what is broken, nothing else

3. Verify in dev
   git push origin hotfix/describe-the-break
   gh workflow run deploy-dev.yml -f branch=hotfix/describe-the-break
   [confirm the fix works]

4. Obtain explicit emergency merge and production approvals; do not infer either
   from the incident
   git checkout main
   git merge hotfix/describe-the-break --no-ff
   git push origin main                          ← this auto-deploys test
   git tag prod-vX.Y.Z && git push origin prod-vX.Y.Z  ← only after approval
```

**Hotfix rules:**
- Hotfixes always branch from `main` — never from a feature branch
- Fix only the broken thing. No opportunistic cleanup. No "while I'm in here..."
- Merge back to main immediately so test stays current with prod
- Document in the commit message that this is a hotfix and why it bypassed normal flow
- If the hotfix temporarily breaks test, that is acceptable — fix it on the next regular cycle

---

## Emergency Patch (something is broken mid-feature, blocking current work)

Same as hotfix, just scoped to unblock active work rather than a prod incident. Same rules apply: branch, minimal fix, dev verify, merge to main, tag if needed.

The distinction is only semantic — the process is identical.

---

## Version Numbering — `MAJOR.MINOR.PATCH`

| Segment | When to bump | Reset on bump |
|---------|-------------|---------------|
| **MAJOR** | Breaking changes, full architecture overhaul, major new system | MINOR and PATCH → 0 |
| **MINOR** | New feature, new endpoint, new module, meaningful new capability | PATCH → 0 |
| **PATCH** | Bug fix, hotfix, data/content change, config tweak, docs | — |

**In practice:** most day-to-day work bumps PATCH. A shipping milestone bumps MINOR. MAJOR is rare.

Tag format: `prod-vMAJOR.MINOR.PATCH` (e.g. `prod-v0.1.6`)

---

## Key Rules — Never Break These

1. **Never commit directly to `main`** — always a branch + merge, even for a 1-line fix
2. **Never skip the branch step** — hotfixes still get branches, just shorter ones
3. **main is always test-deployable** — if main is broken, that is a P0
4. **Tags are permanent** — never reuse or force-push a tag
5. **Hotfix ≠ license for scope creep** — fix the one thing, ship it, move on
6. **Dev and test verify before prod tag** — exceptions require explicit,
   recorded emergency approval

---

## Quick Reference

```bash
# --- NORMAL FEATURE ---
git checkout main && git pull
git checkout -b codex/parent-issue-title
# ... work ...
git push origin codex/parent-issue-title
gh workflow run deploy-dev.yml -f branch=codex/parent-issue-title  # verify in dev
# obtain explicit merge approval
git checkout main && git merge codex/parent-issue-title --no-ff && git push origin main  # → test
# verify test and obtain separate production approval
git tag prod-vX.Y.Z && git push origin prod-vX.Y.Z       # → prod

# --- HOTFIX ---
git checkout main && git pull
git checkout -b hotfix/what-is-broken
# ... minimal fix ...
git push origin hotfix/what-is-broken
gh workflow run deploy-dev.yml -f branch=hotfix/what-is-broken  # verify
git checkout main && git merge hotfix/what-is-broken --no-ff && git push origin main
git tag prod-vX.Y.Z && git push origin prod-vX.Y.Z
```

---

## Adapting to a New Project

When setting up CI/CD for a new project, the three-workflow pattern should mirror this structure:

| File | Trigger | Target |
|------|---------|--------|
| `deploy-dev.yml` | `workflow_dispatch` with `branch` input | dev environment |
| `deploy-test.yml` | `push: branches: [main]` | test environment |
| `deploy-prod.yml` | `push: tags: ['prod-v*']` | production environment |

Each workflow should: checkout the branch/tag → build → copy to server → restart container → health check.

---

*Last updated: 2026-07-28*
