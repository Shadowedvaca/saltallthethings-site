# Isolated Test Environment

Issue #12 provisions Salt All The Things on the shared `my-web-apps-test`
server as the integration gate for an explicitly approved commit on `main`.
It does not share application state, database storage, credentials, or
deployment controls with development or production.

## Reserved resources

| Resource | Test value |
|---|---|
| Host | `my-web-apps-test` |
| Application path | `/opt/satt-platform` |
| Compose project | `satt-test` |
| Loopback application port | `127.0.0.1:8300` |
| Database volume | `satt-test-postgres` |
| Public origin | `https://test.saltallthethings.com` |
| Runtime environment | `test` |

Port `8300` is reserved for SATT on both shared non-production servers. Port
`8200` is already used by the Shadowedvaca test application and must not be
reused.

## Isolation contract

- `compose.yaml` creates the SATT-only database service and private Compose
  network. PostgreSQL has no host port.
- `compose.test.yaml` fixes the project/image names, runtime and database
  ownership, database volume, canonical origin, and loopback-only binding.
- The application receives database host `database` from Compose. It cannot
  receive a development or production `DATABASE_URL` from the server
  environment.
- `ENVIRONMENT` and `DATABASE_ENVIRONMENT` are both fixed to `test`.
  Application startup validates them before Alembic opens a connection.
- Google OAuth values are forced empty and external-service opt-in is forced
  false. Test smoke must not use production credentials or Drive resources.
- The test database starts without AI provider credentials. Any later
  authorized provider configuration must use a test-only credential, remain
  server-side, and receive separate smoke-test authorization.
- The deployment workflow operates only in `/opt/satt-platform` and the
  `satt-test` Compose project. It does not prune global Docker state or restart
  another application's containers.

## Server bootstrap

Bootstrap is a one-time, explicitly authorized operator action:

1. Clone the public repository into `/opt/satt-platform`.
2. Create `/opt/satt-platform/.env` owned by `root:root` with mode `0600`.
3. Configure test-only values for:

   - `SATT_DB_NAME` (`satt_test`)
   - `SATT_DB_USER` (`satt_test`)
   - `SATT_DB_PASSWORD`
   - `SATT_APP_PORT` (`8300`)
   - `SECRET_KEY`

4. Leave `DATABASE_URL`, server-to-server export credentials, and all Google
   OAuth values unset. Set `ALLOW_NONPRODUCTION_EXTERNAL_SERVICES=false`.
5. Add an nginx site for `test.saltallthethings.com` that proxies only to
   `http://127.0.0.1:8300` and forwards the standard proxy headers.
6. Point the test DNS record to `my-web-apps-test`, validate nginx, and obtain a
   certificate for `test.saltallthethings.com`.

Never print, source with shell tracing, commit, or copy `.env` contents into
workflow logs.

## GitHub deployment controls

The repository needs a `test` GitHub environment and these configured secret
names:

- `TEST_HOST`
- `DEPLOY_SSH_KEY`
- `TEST_SSH_KNOWN_HOSTS`

`TEST_SSH_KNOWN_HOSTS` pins the shared test host key. The workflow never uses
`ssh-keyscan` to trust a key observed during deployment.

`.github/workflows/deploy-test.yml`:

1. runs only for a pushed commit on `main`;
2. checks out and records exactly `github.sha`;
3. connects using strict known-host verification;
4. fetches and checks out only that immutable commit on the server;
5. creates a compressed SATT-only pre-deploy database backup when a database
   already exists;
6. builds the shared image and starts only the `satt-test` services;
7. waits for Compose health and verifies local/public metadata report `test`,
   version `0.0.5`, and the exact commit;
8. verifies Alembic revision `0008`;
9. runs ephemeral registration, login/reload, protected export, public-route,
   and unauthenticated-rejection checks and removes the temporary identity; and
10. prints at most 100 lines of SATT app/database logs on failure.

Child approval does not authorize a merge or test deployment. The workflow
runs only after the cumulative pull request receives separate merge approval.

## Data reset and operator access

- Test data is intentionally separate from development and production.
- Deployment preserves test data and makes a bounded pre-deploy backup; it does
  not reseed or replace operator-created test fixtures.
- The deployment smoke creates only one random, non-admin identity and
  short-lived invite. Both are removed before success or failure is reported.
- A full test-data reset requires a verified backup and separate destructive
  approval before removing `satt-test-postgres`.
- Operator accounts and invite codes must be test-only. Do not reuse a
  production password, invite, token, or database export.

## Validation

After each approved `main` deployment:

1. Verify `/api/health` reports status `ok`, environment `test`, version
   `0.0.3`, and the exact merge commit.
2. Verify migration revision `0008` and both Compose services are healthy.
3. Verify public pages and public API routes.
4. Sign in with a test-only account and verify protected pages, persistence,
   reload behavior, and the active release acceptance behavior.
5. Confirm browser requests remain same-origin under
   `test.saltallthethings.com`.
6. Confirm no production/development API, database, OAuth credential, AI
   credential, server-to-server export key, or Drive resource is configured or
   contacted.
7. Reload and repeat important persistence and authentication checks.

## Rollback and recovery

- Repeat deployments store compressed pre-deploy backups under
  `/opt/satt-platform/backups` with mode `0600`. Only SATT test backups older
  than 14 days are removed.
- A code-only rollback checks out a previously validated `main` commit,
  rebuilds `satt:test`, and starts the same `satt-test` Compose project.
- If a failed deployment applied an incompatible migration, stop the SATT test
  project, restore its latest pre-deploy backup into only
  `satt-test-postgres`, then redeploy the matching code commit.
- Never restore a test backup into development or production.
- Removing `satt-test-postgres` is destructive and requires a separate explicit
  confirmation after a backup is verified.
