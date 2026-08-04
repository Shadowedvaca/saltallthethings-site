# Isolated Development Environment

Issue #11 provisions Salt All The Things on the shared
`my-web-apps-dev` server without sharing application state, database storage,
credentials, or deployment controls with test or production.

## Reserved resources

| Resource | Development value |
|---|---|
| Host | `my-web-apps-dev` |
| Application path | `/opt/satt-platform` |
| Compose project | `satt-development` |
| Loopback application port | `127.0.0.1:8300` |
| Database volume | `satt-development-postgres` |
| Public origin | `https://dev.saltallthethings.com` |
| Runtime environment | `development` |

Port `8300` is reserved for SATT on both shared non-production servers. Port
`8200` is already used by the Shadowedvaca development and test application and
must not be reused.

## Isolation contract

- `compose.yaml` creates the SATT-only `database` service and private Compose
  network. PostgreSQL has no host port.
- `compose.development.yaml` fixes the project name, image name, environment,
  database volume, canonical origin, and loopback-only application binding.
- The application receives database host `database` from Compose. It cannot
  receive a production or test `DATABASE_URL` from the server environment.
- `ENVIRONMENT` and `DATABASE_ENVIRONMENT` are both fixed to `development`.
  Application startup validates them before Alembic opens a connection.
- Google OAuth values are forced empty and external-service opt-in is forced
  false. Development smoke tests must not use production Drive resources.
- The development database begins without AI provider credentials. Any later
  authorized provider configuration must use a development-only credential and
  remain server-side.
- The deployment workflow operates only in `/opt/satt-platform` and the
  `satt-development` Compose project. It does not prune global Docker images or
  restart another application's containers.

## Server bootstrap

Bootstrap is a one-time, explicitly authorized operator action:

1. Clone the public repository into `/opt/satt-platform`.
2. Create `/opt/satt-platform/.env` owned by `root:root` with mode `0600`.
3. Configure development-only values for:

   - `SATT_DB_NAME` (`satt_development`)
   - `SATT_DB_USER` (`satt_development`)
   - `SATT_DB_PASSWORD`
   - `SATT_APP_PORT` (`8300`)
   - `SECRET_KEY`

4. Leave `DATABASE_URL` and all Google OAuth values unset. Set
   `ALLOW_NONPRODUCTION_EXTERNAL_SERVICES=false`.
5. Add an nginx site for `dev.saltallthethings.com` that proxies only to
   `http://127.0.0.1:8300` and forwards the standard proxy headers.
6. Point the development DNS record to `my-web-apps-dev`, validate nginx, and
   obtain a certificate for `dev.saltallthethings.com`.

Never print, source with shell tracing, commit, or copy the `.env` contents into
workflow logs.

## GitHub deployment controls

The repository needs a `development` GitHub environment and these configured
secret names:

- `DEV_HOST`
- `DEPLOY_SSH_KEY`
- `DEV_SSH_KNOWN_HOSTS`

`DEV_SSH_KNOWN_HOSTS` pins the shared development host key. The workflow never
uses `ssh-keyscan` to trust a key observed during deployment.

`.github/workflows/deploy-dev.yml`:

1. accepts an explicit `codex/*` branch;
2. resolves that branch through read-only checkout to one immutable commit;
3. connects using strict known-host verification;
4. fetches and checks out only the resolved commit on the server;
5. creates a compressed, SATT-only pre-deploy database backup when a database
   already exists;
6. builds the shared application image and starts only the
   `satt-development` services;
7. waits for Compose health and verifies local and public health report
   `development`, version `0.0.6`, and the exact resolved commit; and
8. prints at most 100 lines of SATT app/database logs on failure.

Manual dispatch:

```text
gh workflow run deploy-dev.yml \
  -f branch=codex/establish-cleanup-environment-isolation-and-release-engineering
```

## Validation

After each deployment:

1. Verify `/api/health` reports status `ok`, environment `development`, version
   `0.0.6`, and the dispatched commit.
2. Verify public pages and public API routes.
3. Sign in with a development-only account and verify protected pages,
   persistence, reload behavior, migrations, and the active child's acceptance
   behavior.
4. Confirm browser requests remain same-origin under
   `dev.saltallthethings.com`.
5. Confirm no production/test API, database, OAuth credential, AI credential,
   or Drive resource is configured or contacted.
6. Reload and repeat the important persistence checks.

## Rollback and recovery

- Every repeat deployment stores a compressed pre-deploy database backup under
  `/opt/satt-platform/backups` with mode `0600`. Backups older than 14 days are
  removed only from that SATT directory.
- A code-only rollback checks out a previously validated SATT commit, rebuilds
  `satt:development`, and starts the same development Compose project.
- If the failed deployment applied an incompatible migration, stop the SATT
  project, restore its latest pre-deploy backup into only
  `satt-development-postgres`, then redeploy the matching code commit.
- Never restore a development backup into test or production.
- To remove the development application, stop the SATT Compose project first.
  Removing `satt-development-postgres` is destructive and requires a separate
  explicit confirmation after a backup is verified.
