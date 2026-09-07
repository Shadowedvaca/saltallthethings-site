# Salt All The Things — Pending Release

## Highlights

- Stale transcription jobs can be recovered without resetting unrelated active work or starting a duplicate transcription.

## Fixes/Changes

- Transcription workers atomically claim one queued or stale job and renew a bounded lease while WhisperX runs.
- The Post-Production page identifies an expired lease and gives administrators a targeted reset for that selected row.
- Claim authority stays server-side and watcher-only endpoints require an administrator session.

## Validation

- Focused transcription contract, watcher, CRUD, route, authorization, and targeted-recovery tests pass against a disposable isolated PostgreSQL container (30 passed).
- The complete migration-backed Python suite passes (365 passed), and all critical Playwright journeys pass in the pinned runner (8 passed), including selected-row stale-job recovery.
- Python compilation, JavaScript syntax, frontend contracts, release validation, repository documentation validation, and the CI application-image build pass.
- Manual UI validation is scheduled once on the final cumulative development artifact under Parent timing.

## Deployment/Migrations

- No database migration is required; lease and recovery metadata use the existing transcription-job JSON record.
- The recording-PC watcher must deploy from the same compatible commit and use an administrator SATT account for its job lifecycle API calls.

## Rollback

- Stop the lease-aware watcher before returning the application and watcher to a previously validated compatible artifact. Existing job status remains readable and added lease metadata is ignored by prior code.

## Known Limitations

- Recovery depends on the recording watcher renewing its three-minute lease every 30 seconds; a job with no valid legacy timestamp is intentionally not declared stale automatically.
