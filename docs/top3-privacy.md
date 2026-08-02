# Top 3 privacy and data contract

Top 3 planning separates shared concept material from participant-owned picks.
The FastAPI service, not the browser, decides which fields a viewer may receive.
Top 3 records are intentionally absent from the general `/api/export`,
`/api/import`, and `Storage` cache contracts.

## Threat model and ownership

- Any authenticated participant may read shared concept fields: name,
  description, rules, host notes, AI example, lifecycle state, and provenance.
- An account submission belongs to the authenticated user ID from the signed
  token. Request bodies cannot select or replace the owner.
- The owner receives their three picks and private discussion notes. Other
  account viewers receive only contributor identity and completion metadata
  until a reveal row exists for that specific viewer and submission.
- Administrator status does not bypass participant redaction.
- External submissions have no account owner, retain a guest or listener type
  plus the entering account for audit, and are shared episode results. Their
  write routes are intentionally deferred to child #29.
- Reveal creation is intentionally deferred to child #29. The viewer-scoped
  projection already honors persisted reveal rows without making them global.

## Schema

Alembic revision `0008` adds:

- `satt.top3_concepts`: reusable shared definitions, lifecycle state, optional
  validated AI example and provenance, author, and timestamps;
- `satt.top3_assignments`: one concept per episode idea;
- `satt.top3_submissions`: account-owned or external submissions with exactly
  three non-empty, case-insensitively distinct ranked picks and optional private
  discussion notes; and
- `satt.top3_reveals`: irreversible viewer/submission audit records.

The database uses a partial unique index to allow at most one account
submission per assignment and user. Check constraints enforce participant
identity shape and pick integrity even if application validation is bypassed.

## Authenticated API

- `GET /api/top3/concepts` returns shared concepts only.
- `POST /api/top3/concepts`, `PUT /api/top3/concepts/{id}`, and
  `DELETE /api/top3/concepts/{id}` manage shared definitions. Assigned concepts
  cannot be deleted.
- `GET /api/top3/episodes/{ideaId}` returns the viewer-scoped assignment and
  contributor projection.
- `PUT` or `DELETE /api/top3/episodes/{ideaId}/assignment` atomically replaces
  or removes an assignment.
- `PUT` or `DELETE /api/top3/episodes/{ideaId}/submission` affects only the
  authenticated user's submission.

Mutations use the existing `If-Match` data revision guard. Responses carry the
new revision, while hidden Top 3 content remains outside the general export
payload used to obtain that revision.

## Episode preparation workflow

Show Management loads Top 3 planning through the dedicated viewer-scoped API,
not through the shared `Storage` cache. An authenticated host may assign an
active banked concept, replace or remove the current assignment, and save one
owner-bound submission containing exactly three distinct ranked picks plus
optional private discussion notes. The expanded episode summary displays the
shared concept name, description, rules, and clearly separated fictional AI
example. The full-screen show display repeats those shared fields as read-only
planning material without rendering participant submissions.

Contributor readiness lists account display names and Ready/Waiting state only.
The page renders picks and private notes only for the current user's submission,
even if a future reveal makes additional fields available from the API. A
revision conflict reloads the latest assignment and requires the host to review
before retrying. Replacement and removal confirmations explicitly warn that all
submissions tied to the old assignment will be deleted.

## Lifecycle and rollback

- Replacing or removing an episode assignment deletes its submissions and
  viewer reveals in the same transaction because those picks apply only to the
  former concept.
- Deleting an idea cascades its Top 3 assignment, submissions, and reveals.
- Deleting an unassigned concept is allowed; deleting an assigned concept is
  rejected. Retired concepts cannot be newly assigned.
- User deletion is restricted while the user owns, entered, assigned, authored,
  or revealed Top 3 records, preserving attribution and audit history.
- Deleting a submission cascades its reveal rows.
- Downgrading from `0008` to `0007` drops all four Top 3 tables. Take and verify
  an environment-specific backup before downgrade once Top 3 records exist.

The deployment workflows rehearse `0008` to `0007` to `0008` against an
isolated database. Restoring a database backup is destructive and remains a
separately approved recovery action.
