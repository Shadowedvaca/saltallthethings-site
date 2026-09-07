# Transcription Job Recovery

SATT queues transcription work in each show slot's `transcription_job` record.
The recording-PC watcher polls only for queued work or an expired watcher lease;
it must atomically claim a job before starting WhisperX.

## Lease contract

- A successful claim changes one `pending` job to `in_progress`, issues an
  opaque claim token, and creates a three-minute lease.
- The watcher renews that lease every 30 seconds while the transcription
  subprocess runs. Only the owning claim token can renew or finish the job.
- A second watcher receives a conflict while the lease is active. Duplicate or
  late finish requests also receive a conflict and cannot replace canonical
  state.
- An `in_progress` job is stale only when its explicit `leaseExpiresAt` has
  passed. Older records without an explicit lease use `updatedAt` plus the same
  three-minute interval. Records with no valid timestamp are not automatically
  declared stale.
- If a watcher cannot renew its lease, it terminates its local subprocess. A
  later watcher may recover the job only after the last confirmed lease expires.

Queue listings and browser responses never include the claim token. They retain
bounded operational metadata such as status, attempt count, claim time, lease
deadline, reset/recovery count, and whether the server currently considers the
job stale. No credentials or transcription content are stored in this record.

## Authorization and targeted recovery

Any authenticated SATT account may queue transcription. The recording watcher
uses an administrator account to list, claim, renew, and finish work; the
server rejects ordinary user sessions before checking job metadata, and its
atomic state and claim-token checks remain authoritative.

Manual recovery is restricted to administrators. On the Post-Production page,
an administrator can select **Reset selected job** only for the stale row. The
endpoint locks and changes that one slot from `in_progress` to `pending`. It
rejects active leases and never resets other jobs. Non-admin users see recovery
guidance and receive `403` if they call the reset endpoint directly.

The watcher does not bulk-reset jobs during startup. Its normal poll includes a
stale job as a claim candidate, and the same atomic claim transition records the
recovery before work begins.

## Operator recovery

1. Confirm the Post-Production row says the lease expired; do not infer
   staleness merely because processing is slow.
2. Check the bounded watcher log for the slot identifier, claim/heartbeat
   failure, and subprocess exit result. Do not copy credentials or recording
   content into an issue or release record.
3. If the prior watcher is still running, stop that watcher cleanly and wait for
   the displayed lease deadline.
4. As a SATT administrator, reset only the selected stale row. Reload the page
   and confirm that row is queued while unrelated active rows are unchanged.
5. Start or retain one watcher and confirm it claims the queued job. If the job
   fails because its audio is missing, restore the expected local recording and
   use the ordinary retry action.

## Rollback

This change uses the existing JSONB column and requires no database migration.
A code rollback to a compatible prior application and watcher artifact leaves
the stored metadata readable; prior code uses the `status` field and ignores
the additional lease fields. Before rollback, stop the lease-aware watcher so a
prior watcher cannot run concurrently with an active leased claim. Preserve the
normal environment backup and deployment evidence defined in the development,
test, and production runbooks.
