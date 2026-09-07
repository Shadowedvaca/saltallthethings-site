# Salt All The Things — Pending Release

## Highlights

- Stale transcription jobs can be recovered without resetting unrelated active work or starting a duplicate transcription.
- Authenticated clients can receive minimal committed-revision hints without exposing protected canonical records.

## Fixes/Changes

- Transcription workers atomically claim one queued or stale job and renew a bounded lease while WhisperX runs.
- The Post-Production page identifies an expired lease and gives administrators a targeted reset for that selected row.
- Claim authority stays server-side and watcher-only endpoints require an administrator session.
- A resource-bounded SSE endpoint reports only the canonical-state revision, rechecks account authorization, and closes without retaining background subscriptions.
- A reusable browser coordinator coalesces newer revisions into canonical reloads, ignores duplicate/out-of-order/self-originated signals, catches up after reconnect, and tears down streams and retry timers with the authentication/page lifecycle.
- Show Management, Config, Joke Bank, Song Bank, and Guest Bank now repaint clean canonical views automatically while preserving form drafts and edit sessions behind explicit continue-editing or discard-and-load-latest decisions.
- Show content editing separates independently saved schedule, assignment, and Top 3 controls so those actions cannot rebuild a card and discard unsaved content; Top 3 privacy data remains outside canonical-state reconciliation.

## Validation

- Focused transcription contract, watcher, CRUD, route, authorization, and targeted-recovery tests pass against a disposable isolated PostgreSQL container (34 passed).
- Focused notification tests pass for authentication, resource authorization, commit/rollback visibility, payload minimization, heartbeat behavior, revocation, expiry, and disconnect cleanup (8 passed).
- Deterministic client tests use a fake transport, clock, canonical loader, and abort controller to cover retry/backoff, missed-event catch-up, coalescing, ordering, self-originated signals, dirty/conflicted states, auth termination, SSE parsing, and teardown.
- Deterministic view-adapter tests cover multiple dirty scopes, retained edits, explicit discard, canonical retry, accessible status, and conflict priority across transport loss; browser coverage includes a two-context Song Bank conflict and the existing mutation-conflict journey now proving draft preservation before explicit canonical repaint.
- The cumulative migration-backed Python suite passes (378 passed) with 67.35% overall and 99.57% changed-line coverage, and all critical Playwright journeys pass in the pinned runner (10 passed), including selected-row stale-job recovery, clean Song/Guest convergence, and explicit preservation of a dirty Song Bank draft across a newer revision.
- Python compilation, JavaScript syntax, frontend contracts, release validation, repository documentation validation, and the CI application-image build pass.
- Manual UI validation is scheduled once on the final cumulative development artifact under Parent timing.

## Deployment/Migrations

- No database migration is required; lease and recovery metadata use the existing transcription-job JSON record.
- The recording-PC watcher must deploy from the same compatible commit and use an administrator SATT account for its job lifecycle API calls.
- Revision notification uses the existing app, same-origin API, and environment-bound PostgreSQL database; it adds no migration, broker, credential, port, or provider contact.

## Rollback

- Stop the lease-aware watcher before returning the application and watcher to a previously validated compatible artifact. Existing job status remains readable and added lease metadata is ignored by prior code.

## Known Limitations

- Recovery depends on the recording watcher renewing its three-minute lease every 30 seconds; a job with no valid legacy timestamp is intentionally not declared stale automatically.
- Notification is a reload hint rather than a data channel. A user who keeps editing intentionally sees the last acknowledged list/count/control state until saving, cancelling, or accepting the newer canonical revision.
- Top 3 Bank and Post-Production retain their separate viewer-scoped revision and job-polling lifecycles; neither is adapted through canonical-state page reconciliation.
