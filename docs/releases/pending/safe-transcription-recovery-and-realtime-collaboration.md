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
- Revision-stream lifecycle logs now expose only a fixed resource and bounded close reason, while cumulative recovery coverage proves every eligible workflow, capped reconnect behavior, and deployed privacy/authentication boundaries.

## Validation

- Focused transcription contract, watcher, CRUD, route, authorization, and targeted-recovery tests pass against a disposable isolated PostgreSQL container (34 passed).
- Focused notification tests pass for authentication, resource authorization, commit/rollback visibility, payload minimization, heartbeat behavior, revocation, expiry, disconnect cleanup, and payload-free lifecycle logging (9 passed).
- Deterministic client tests use a fake transport, clock, canonical loader, and abort controller to cover retry/backoff, missed-event catch-up, coalescing, ordering, self-originated signals, dirty/conflicted states, auth termination, SSE parsing, and teardown.
- Deterministic view-adapter tests cover multiple dirty scopes, retained edits, explicit discard, canonical retry, accessible status, and conflict priority across transport loss; browser coverage includes a two-context Song Bank conflict and the existing mutation-conflict journey now proving draft preservation before explicit canonical repaint.
- Cumulative browser coverage exercises clean convergence and reload on Config, Joke Bank, Song Bank, Guest Bank, and Show Management, then proves an interrupted stream catches up after the server returns. Deterministic tests prove repeated failures retain one retry timer and cap backoff at 30 seconds.
- Development/test deployment smoke verifies unauthenticated stream rejection, authenticated immediate catch-up, exact minimal payload shape, and rejection of a Top 3-shaped resource using only synthetic identities and environment-local services.
- The cumulative migration-backed Python suite passes (379 passed) with 67.43% overall and 99.18% changed-line coverage, and all critical Playwright journeys pass in the pinned runner (11 passed), including selected-row stale-job recovery, five-workflow convergence, interrupted-stream recovery, and explicit preservation of a dirty Song Bank draft across a newer revision.
- Python compilation, JavaScript syntax, frontend contracts, release validation, repository documentation validation, and the CI application-image build pass.
- Manual UI validation is scheduled once on the final cumulative development artifact under Parent timing.

## Deployment/Migrations

- No database migration is required; lease and recovery metadata use the existing transcription-job JSON record.
- The recording-PC watcher must deploy from the same compatible commit and use an administrator SATT account for its job lifecycle API calls.
- Revision notification uses the existing app, same-origin API, and environment-bound PostgreSQL database; it adds no migration, broker, credential, port, or provider contact.
- One page owns at most one stream, which performs one short-lived account/revision query per second and one payload-free heartbeat per 15 idle seconds. The current single-worker service is sized for the small operator group, not unmeasured high fan-out.

## Rollback

- Stop the lease-aware watcher before returning the application and watcher to a previously validated compatible artifact. Existing job status remains readable and added lease metadata is ignored by prior code.

## Known Limitations

- Recovery depends on the recording watcher renewing its three-minute lease every 30 seconds; a job with no valid legacy timestamp is intentionally not declared stale automatically.
- Notification is a reload hint rather than a data channel. A user who keeps editing intentionally sees the last acknowledged list/count/control state until saving, cancelling, or accepting the newer canonical revision.
- Top 3 Bank and Post-Production retain their separate viewer-scoped revision and job-polling lifecycles; neither is adapted through canonical-state page reconciliation.
- Application and static assets must roll back together to a prior compatible exact-SHA artifact. No collaboration data rollback is required; higher concurrency requires target-environment capacity measurement first.
