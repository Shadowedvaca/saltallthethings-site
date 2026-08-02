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
  plus the original entering account for audit, and are shared episode results.
  Any authenticated host may add, edit, or remove them; editing never changes
  the original entry attribution.
- An authenticated viewer may deliberately and irreversibly reveal another
  account's completed submission only to that viewer. The audit row records the
  viewer, submission, and timestamp. Repeating the request is idempotent, and
  neither administrator status nor one viewer's reveal makes the data global.

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
- `POST /api/top3/episodes/{ideaId}/reveals/{submissionId}` creates the
  viewer-specific reveal audit record. It rejects the viewer's own submission,
  external results, and submissions from another episode.
- `POST /api/top3/episodes/{ideaId}/external-submissions` and `PUT` or `DELETE`
  on `/api/top3/episodes/{ideaId}/external-submissions/{submissionId}` manage
  shared guest/listener results. Bodies cannot select an account owner or alter
  the original entering account.
- `POST /api/top3/episodes/{ideaId}/spotify-results` with the exact purpose
  `spotify-overview` is the deliberate authenticated publication boundary. It
  returns only the list name and each submitted contributor's display name and
  three picks. It omits missing accounts and every note, definition field,
  example, participant type, identifier, timestamp, and reveal field.

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
example. The full-screen show display repeats those shared fields and renders
the current account's submission, viewer-revealed account submissions, shared
external results, and metadata-only Ready/Waiting state for all other accounts.

Contributor readiness lists account display names and Ready/Waiting state.
Completed submissions remain hidden until the viewer confirms an irreversible,
viewer-only reveal; cancelling the confirmation sends no request. Revealed picks,
notes, and timestamps render only from that viewer's projection. The page also
captures exact-three shared guest/listener results and states that any
authenticated host may edit or remove them. A revision conflict reloads the
latest assignment and requires the host to review before retrying. Replacement
and removal confirmations explicitly warn that all submissions tied to the old
assignment will be deleted.

## Show summary and Spotify publication boundary

The full-screen show summary continues to use only the viewer-scoped preparation
projection. Opening it does not create reveal rows: hidden account lists remain
status-only, while the current account, lists already revealed to that viewer,
and shared external results render as read-only preparation material.

Opening the authenticated full-screen display separately requests the narrow
Spotify result contract for composition. That response deliberately includes
every completed account, guest, and listener list, regardless of preparation
reveal state, but contains only `listName`, `displayName`, and exactly three
ranked pick strings. Account usernames are display-cased without changing their
stored login value. Submitted accounts are ordered first, case-insensitively by
display name and then picks, followed by external contributors using the same
ordering; accounts without a saved submission are omitted. Composition normalizes
line-breaking whitespace so a name or pick cannot alter the compact format. The
response is held only for the selectable Spotify overview and copy operation,
never inserted into the preparation cache or projection.

Requesting, composing, rendering, and copying results are read-only. They do not
bump the data revision, create a reveal, modify any Top 3 record, or publish to
Spotify. Clipboard API failure uses the existing browser-copy fallback and
reports accessible success or failure status.

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
