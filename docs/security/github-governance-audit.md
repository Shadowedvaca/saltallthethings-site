# GitHub governance audit

Audit date: 2026-07-28

Only names, presence, and protection metadata were inspected. No secret value
was read or logged.

## Observed repository state

- Repository visibility: public.
- Default branch: `main`.
- Rulesets: none.
- `main` branch protection: not configured.
- Default GitHub Actions token permission: read.
- Actions may not approve pull-request reviews.
- Open pull requests: none at the start of Foundation work.
- Production tags and GitHub Releases: none.
- GitHub environments: only `github-pages`.
- Repository Actions variables: none.
- `github-pages` environment secrets: none.

## Repository secret-name presence

| Name | Present |
|---|---|
| `DEV_HOST` | No |
| `TEST_HOST` | No |
| `PROD_HOST` | No |
| `DEPLOY_SSH_KEY` | No |
| `STAGING_SSH_KEY` | Yes, legacy |
| `STAGING_SSH_KNOWN_HOSTS` | Yes, legacy |
| `SATT_API_URL` | Yes, legacy |

GitHub does not permit reading an existing Actions secret value. The legacy SSH
key therefore cannot be copied or renamed by inspection; the standard secret
must be supplied or independently replaced through an explicitly authorized
key-rotation procedure.

## Required authorized configuration

The following settings are required for the intended contract but were not
changed during the read-only audit:

1. Create `development`, `test`, and `production` environments.
2. Restrict development deployments to approved feature branches.
3. Restrict test deployments to the approved `main` commit.
4. Restrict production deployments to validated `prod-v*` tags and the
   separately approved production-release action.
5. Create and presence-check `DEV_HOST`, `TEST_HOST`, `PROD_HOST`, and
   `DEPLOY_SSH_KEY`.
6. Retire legacy names only after every consuming workflow has moved to the
   standard names and connectivity has been verified.

These mutations require explicit authorization. Server, DNS, and secret values
also depend on the later provisioning and cutover issues and must not be
invented during repository governance work.
