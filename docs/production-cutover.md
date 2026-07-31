# Production container cutover

This runbook defines the controlled replacement of the legacy SATT systemd
runtime with the repository's isolated production container. It is not approval
to perform the cutover. Creating the GitHub `production` environment, changing
server configuration, creating `prod-v0.0.1`, or deploying production each
requires the explicit authorization described in the release process.

## Safety boundary

- The workflow runs only for an immutable `prod-vX.Y.Z` tag whose version,
  curated notes, tag target, and `main` ancestry validate.
- `compose.production.yaml` is used by itself. It starts only
  `satt-production-app`, publishes only the configured loopback application
  port, and does not create or move a database.
- The existing production PostgreSQL database remains authoritative. The
  container reaches that host database through `host.docker.internal`; host
  backup tools reach the same database locally.
- SATT's systemd unit and current reverse-proxy configuration remain available
  for a 24-hour rollback window after the first successful container cutover.
- Do not change or restart PATT, Shadowed Vaca, any other application, database,
  Compose project, systemd unit, Nginx site, certificate, or virtual host.
- Never print environment-file contents, database connection values, OAuth or AI
  values, authentication hashes, invite codes, or record contents. Validation
  reports configured status, counts, exact release metadata, and one-way
  SHA-256 fingerprints only.

## Required inventory and preflight

A production operator must complete this secret-safe inventory immediately
before approving the production tag:

1. Record the active SATT systemd unit name, active state, process owner,
   repository path, working directory, command, loopback port, and exact commit.
2. Record the SATT Nginx site name, enabled state, upstream loopback port, public
   hostname, and certificate status. Do not display unrelated virtual-host
   contents.
3. Confirm whether SATT's current static files are served by the application or
   Nginx and record only their bounded paths and ownership.
4. Confirm the production database service is local, healthy, and owned by the
   production tier. Record its engine/version, database and role presence, and
   configured status without printing names, connection values, or credentials.
5. Record the current user, invite, configuration, idea, joke, show-slot, and
   assignment counts plus the secret-safe authentication and data fingerprints.
6. Confirm Docker, the Compose plugin, Git, curl, Python 3, `pg_dump`,
   `pg_restore`, and systemd are available. Confirm the release checkout and
   backup directories are root-only.
7. Confirm `/opt/satt-platform/.env.production` exists with mode `0600`, is
   owned by the production operator, declares matching production runtime and
   database tiers, and targets the local host database alias. Do not display it.
8. Confirm the intended SATT loopback port does not collide with another service
   and that the existing Nginx upstream can reach it without changing any other
   site.

The current repository-side review could not complete the live inventory:
existing local SSH identities were rejected by the production host. That is a
hard preflight gate, not a reason to guess. A separately authorized operator
with production access must complete and record it before tag approval.

## GitHub production controls

Create the protected GitHub `production` environment only with separate
approval. It must require the repository's production reviewers and contain
these secret names:

- `PROD_HOST`
- `DEPLOY_SSH_KEY`
- `PROD_SSH_KNOWN_HOSTS`

The server-side `.env.production` file supplies these configuration keys; values
must never be copied into GitHub logs, issues, release notes, or this document:

- `ENVIRONMENT`
- `DATABASE_ENVIRONMENT`
- `DATABASE_URL`
- `SECRET_KEY`
- `SATT_APP_PORT`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_REFRESH_TOKEN`

The first two values must both identify production. OAuth values may remain
empty when the production feature is not configured. The workflow refuses a
non-local database host and strict SSH host verification is mandatory.

## Approved cutover sequence

After development integration, merge, isolated test validation, and explicit
production-release approval, create the exact `prod-v0.0.1` tag on the tested
`main` commit. The tag starts `deploy-prod.yml`; a normal branch push cannot.

The workflow performs this sequence:

1. Validate the canonical tag, authoritative version, curated notes, exact tag
   target, and ancestry from `main`.
2. Establish strict SSH trust from the protected production environment.
3. On the production host, validate tools, mode-`0600` configuration, exact tag
   checkout, standalone Compose expansion, and the local database boundary.
4. Identify either the active legacy SATT systemd unit for the first cutover or
   the exact prior SATT container image for a later release.
5. Create a custom-format PostgreSQL backup in the root-only release backup
   directory, verify it with `pg_restore --list`, and report only its filename
   and SHA-256. This is the first production state-changing operation after
   read-only preflight and happens before image build or runtime interruption.
6. Build the immutable frontend/backend image.
7. Capture pre-migration authentication and stable-data counts and SHA-256
   fingerprints without printing any contents.
8. Stop only the current SATT runtime. Do not disable or delete the systemd
   unit.
9. Start the exact tagged image. Its entrypoint applies Alembic migrations, then
   the workflow verifies all migration heads.
10. Recompute and compare authentication and stable-data fingerprints. Expected
    migration normalization is deliberately excluded; all other differences
    fail the deployment.
11. Verify local and public health report `production`, version `0.0.1`, and the
    exact tagged commit. Diagnostics are limited to 100 SATT application lines.
12. Store only the current tag/commit and prior SATT runtime identifiers in a
    root-only state directory.
13. After the deployment job and independent public health check succeed, invoke
    the separate least-privilege publisher to revalidate the exact tag/commit
    and create or update the curated GitHub Release. A failed deployment cannot
    publish a release.

A failure after the old runtime stops triggers automatic recovery. On the first
cutover the new container is removed, the previous checkout is restored, and
only the SATT systemd unit is restarted. On later container releases, the exact
prior image is restarted with its prior commit metadata. The failed workflow
must remain failed even when recovery succeeds.

## Verification and rollback window

For 24 hours after the first successful cutover:

- keep the SATT systemd unit, legacy checkout, reverse-proxy route, verified
  backup, and rollback state intact;
- monitor bounded application health and confirm registration/login,
  authenticated data access, edits, persistence after reload, and scheduled
  post-production behavior;
- compare authentication and stable-data counts/fingerprints at the approved
  checkpoints; and
- do not prune images or remove old files, the database, or other services.

Test the non-production recovery contract before production approval by forcing
a post-start health mismatch in an isolated environment and verifying that the
prior SATT runtime returns. Do not use production data or credentials for that
exercise.

During the window, an authorized operator may redeploy the recorded prior SATT
runtime if validation fails. Database restoration is destructive and is never
automatic; stop, preserve the failed state, and obtain separate explicit
approval before restoring the verified dump. Migration downgrade or backup
restore instructions must be reviewed against the exact failed release.

After 24 hours of healthy production operation and explicit cleanup approval,
the obsolete SATT systemd runtime and legacy static deployment path may be
retired. Keep the release backup according to the approved retention policy.
Do not move or reuse an immutable production tag; corrections require a new
patch release.
