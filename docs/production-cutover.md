# Production container and database cutover

This runbook defines the controlled replacement of the legacy SATT systemd
runtime and host database connection with an isolated production application and
PostgreSQL Compose pair. It is not approval to merge, tag, deploy, restore,
delete a volume, or retire the rollback source.

The immutable `prod-v0.0.1` attempt failed during pre-cutover fingerprinting
because the application container could not reach PostgreSQL listening only on
the host loopback interface. The workflow stopped before systemd shutdown,
migrations, container startup, static promotion, or GitHub Release publication;
0.0.1 was not shipped. The corrected architecture begins with patch 0.0.2 and
must use a new immutable tag.

## Safety boundary

- `compose.production.yaml` is used by itself. It starts only
  `satt-production-app` and `satt-production-database` on the private
  `satt-production` network.
- The database service uses the explicitly named `satt-production-postgres`
  volume and publishes no host port. The application receives the database
  service name and separate server-side database fields; production Compose
  does not accept an application `DATABASE_URL` fallback.
- The current host PostgreSQL SATT schema remains authoritative until the final
  stopped-runtime backup is verified. It remains unchanged throughout the
  first-cutover rollback window.
- Dumps include only the SATT schema, use PostgreSQL custom format, omit
  ownership and privileges, have mode `0600`, and are verified with
  `pg_restore --list`. Logs report only phase, filename, SHA-256, and verified
  status.
- The frontend is copied from the exact immutable application image into a
  staged directory and atomically replaces the Nginx-served static directory
  only after local application health and data continuity pass.
- The existing SATT systemd unit, prior checkout, prior static directory,
  reverse-proxy route, host database, verified dumps, and rollback state remain
  available throughout the observation window.
- Do not change or restart PATT, Shadowed Vaca, sv-tools, another Compose
  project, another database, another systemd unit, another Nginx site, DNS, or
  certificates.
- Never print environment-file contents, connection values, credentials,
  authentication hashes, invite codes, database rows, or configuration records.
  Validation reports configured status, exact release metadata, counts, and
  one-way SHA-256 fingerprints only.

## Required inventory and preflight

Immediately before a production tag is approved:

1. Record the active SATT runtime type, exact commit, process owner, working
   directory, loopback port, and bounded health metadata.
2. Confirm the SATT Nginx site is enabled, its upstream remains loopback port
   8200, and its static root is `/opt/satt-platform/static`. Validate Nginx
   without displaying unrelated virtual-host configuration.
3. Confirm host PostgreSQL is healthy and local. Record only the SATT schema and
   role configured status, migration revision, table counts, and secret-safe
   authentication/data fingerprints.
4. Confirm Docker, Compose, Git, curl, Python 3, `pg_dump`, `pg_restore`, and
   systemd are available. Confirm backup and state directories are root-only.
5. Confirm `/opt/satt-platform/.env.production` has mode `0600`, declares
   matching production runtime/database tiers, contains the required private
   database fields and a separately named legacy source connection, and does
   not define the application `DATABASE_URL`. Validate values inside the server
   process without printing them.
6. Confirm `satt-production-app`, `satt-production-database`, and
   `satt-production-postgres` do not exist before the first cutover. A leftover
   volume from a failed attempt is evidence to preserve, not authorization to
   delete or overwrite it.
7. Confirm `prod-v0.0.1` remains unchanged and has no GitHub Release. Confirm
   the intended new tag matches `VERSION`, release-note filename and heading,
   exact tested main commit, and protected production policy.
8. Confirm the latest pull-request, fresh-database, isolated restore,
   development, and test checks passed for the exact intended commit.

## Server-side production configuration

The mode-`0600` production environment file supplies these names. Values remain
server-side and must never appear in GitHub logs, issues, release notes, or
terminal transcripts:

- `ENVIRONMENT`
- `DATABASE_ENVIRONMENT`
- `LEGACY_DATABASE_URL`
- `SATT_DB_NAME`
- `SATT_DB_USER`
- `SATT_DB_PASSWORD`
- `SECRET_KEY`
- `SATT_APP_PORT`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_REFRESH_TOKEN`

The legacy source is accepted only by the host-side backup and fingerprint
helpers and must resolve to a local host PostgreSQL endpoint. The application
container constructs its connection internally from `SATT_DB_*` and can reach
only the private `database` service.

## Approved first-cutover sequence

After corrected development integration, explicit merge approval, isolated test
validation, and separate production-release approval, create a new immutable
patch tag on the exact tested main commit. The tag workflow performs:

1. Validate tag/version/notes, exact tag target, and main ancestry.
2. Establish strict SSH trust through the protected production environment.
3. Capture the prior checkout and switch to the exact immutable tag.
4. Validate tools, configuration mode and configured status, production tiers,
   standalone Compose structure, runtime identity, and absence of a prior SATT
   production database volume.
5. Create and verify a live `preflight` SATT-schema dump before image build or
   runtime interruption.
6. Pull PostgreSQL 16, build the exact application image, extract only the
   explicitly public frontend files, and stage them without changing the live
   static directory.
7. Stop only the SATT systemd service. This begins the short production outage.
8. Create and verify a second `final` SATT-schema dump while the application is
   stopped, then compute the source authentication/data fingerprint.
9. Start only the fresh SATT database service, restore the final dump into its
   empty named volume, and compare the restored pre-migration fingerprint to the
   stopped source.
10. Start the exact tagged application image. Its entrypoint validates tier
    ownership and runs `alembic upgrade head`; verify all migration heads and
    compare the post-migration fingerprint.
11. Verify local health reports `production`, the expected version, and exact
    commit.
12. Atomically move the prior static directory into the protected asset history
    and promote the files extracted from the exact application image.
13. Verify public health with the same metadata and load the public landing
    page through Nginx.
14. Record only current tag/commit, prior runtime identifiers, prior static
    path, final backup path, and database volume name in the mode-`0600` state
    directory.
15. Only after deployment and independent public verification succeed may the
    least-privilege publisher create the curated GitHub Release.

## Automatic application rollback

Any failure after SATT is stopped must leave the workflow failed and:

1. remove only failed SATT containers and the SATT Compose network;
2. leave the failed named database volume and both verified dumps intact;
3. restore the prior static directory if asset promotion occurred;
4. restore the prior host-database backup cron if it was switched;
5. check out the recorded prior commit; and
6. restart only the SATT systemd service against the unchanged host database.

Database restoration is never automatic. Do not delete the failed volume,
overwrite either database, restore a dump, or downgrade migrations without
separate explicit approval against the exact failed state. A pre-cutover failure
restores the prior checkout and leaves the active runtime untouched.

## Isolated restore rehearsal

Pull-request validation must exercise the restore mechanism without production
data or credentials:

1. migrate a fresh isolated PostgreSQL database;
2. create and verify a SATT-schema-only custom dump;
3. fingerprint the source;
4. remove and recreate only the isolated database container;
5. restore the dump before application startup;
6. compare restored and post-start fingerprints; and
7. remove all isolated CI resources.

Development and test then validate the corrected immutable commit normally.
The production host database or backup must never be used for this rehearsal.

## Observation window and later releases

For at least 24 hours after the successful first cutover, retain the systemd
unit, host database, prior checkout, prior static directory, final verified
dump, production volume, prior backup cron, and rollback state. Verify the new
nightly job creates a verified container dump, plus registration/login,
authenticated reads and edits, persistence after reload, public pages,
post-production behavior, migration head, and bounded health metadata.

Later container releases back up the private database both before image build
and after stopping the current application, retain the same named volume, and
promote static assets from the new immutable image. Application rollback may
restart the recorded prior image, but database restore remains a separately
approved destructive operation.

After the observation window is healthy, removing the host database source,
legacy systemd runtime, prior static directory, failed volumes, old images, or
release dumps requires an explicit bounded cleanup approval. Never move or reuse
an immutable production tag; corrections require a new patch release.
