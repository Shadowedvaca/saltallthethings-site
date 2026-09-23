# Salt All The Things — Pending Release

## Highlights

- Coordinates development and test deployments with the other applications on
  each shared host so resource-intensive builds and activations cannot overlap.
- Rejects a deployment before active mutation when the shared host lacks the
  agreed disk, swap, or memory headroom.

## Fixes/Changes

- Adds the common `/run/lock/shared-platform-deployment.lock` protocol with a
  bounded 2700-second wait to the SATT development and test workflows.
- Holds the lock across exact-SHA checkout, scoped backup retention, on-host
  build, activation, migrations, health, authenticated smoke, diagnostics, and
  SATT-owned cleanup.
- Preserves repository-level concurrency, strict SSH trust, immutable commit
  evidence, bounded diagnostics, and app-scoped backup and rollback behavior.
- Extends workflow contract tests and operator documentation while leaving the
  production workflow unchanged.

## Validation

- Static workflow tests verify lock scope, admission ordering and thresholds,
  timeout allowance, release evidence, failure propagation, and prohibited
  host-global cleanup operations.
- Repository documentation, release-record validation, focused tests, complete
  CI, and an exact-SHA development deployment are required before review.

## Deployment/Migrations

- Development and test hosts must provide standard `flock`, at least 12 GiB of
  available root filesystem space, at least 1 GiB of configured swap, and at
  least 2 GiB of combined available memory plus free swap at deployment time.
- No schema, data-contract, application configuration, credential, port, DNS,
  or production deployment change is introduced.

## Rollback

- Revert the workflow and documentation commit to restore the prior SATT-only
  deployment sequencing; application rollback continues to use a previously
  validated exact commit and the existing scoped pre-deploy database backup.
- Database restore, volume removal, or any other destructive recovery remains
  separately controlled and is not performed by this change.

## Known Limitations

- Admission thresholds prevent new work when headroom is low but do not reserve
  resources against unrelated processes started after admission.
- The common lock coordinates participating repositories only; manually run
  host mutations must follow the same lock protocol to receive its protection.
