# Guest Bank data and API contract

Guest records and their episode links are private authenticated planning data.
They are included in the authenticated `/api/export` and `/api/import` contract
as `guests` and `guestAssignments`, but never in public episode or homepage
responses.

## Schema and lifecycle

Alembic revision `0009` creates `satt.guests` and
`satt.guest_assignments`. A guest has an opaque ID, required display name,
optional private host notes, `active` or `archived` status, and created/updated
timestamps. The join table uses `(guest_id, idea_id)` as its primary key, so a
guest can appear on many shows and a show can have many guests without duplicate
links.

Archiving retains every existing link but prevents new assignment. Restoring
allows new assignment again. Guest deletion is rejected while any assignment
remains; hosts must explicitly unassign every show first. Deleting an idea
cascades only its join rows and never deletes the reusable guest record.
Repeated assignment and unassignment requests are idempotent. Mutations use the
shared `If-Match` data revision, and guest lifecycle writes are transactionally
serialized to prevent concurrent duplicate links or incorrect counts.

## Appearance statistics

`totalAppearances` counts every current guest-to-idea link. `firstAppearance`
and `mostRecentAppearance` use only shows with a current schedule assignment and
the effective release date (`releaseDateOverride` when present, otherwise
`releaseDate`). Unscheduled links still count but have a `null` release date and
cannot fabricate first or most-recent dates. The authenticated guest response
also includes deterministic `appearanceHistory` entries with idea, title,
schedule, episode, and release-date context.

## Authenticated Guest Bank screen

Hosts manage reusable records at `/guests.html`. The page supports creating and
editing a required display name and optional private host notes, searching
across guest and appearance context, filtering active or archived records, and
archiving or restoring a record without changing its existing appearances.
Guest and show content is escaped before rendering, notes remain inside the
authenticated page, and loading, saving, empty, validation, conflict, and
failure states are announced through keyboard- and screen-reader-compatible
status controls.

Each guest card shows server-derived Total Appearances, First Appearance, Most
Recent Appearance, and an expandable linked-show history. An unscheduled entry
is labeled explicitly and never supplies a false date. Archived cards remain
searchable and retain their complete history while being visually distinct.
Deletion requires confirmation and is blocked with actionable guidance until
all show assignments have been removed. Assignment controls themselves remain
in the separate show-management delivery child.

## Import, privacy, and rollback

Legacy imports that omit both guest keys preserve current Guest Bank data.
Imports that include guest links must reference existing guest and idea IDs,
must not contain duplicate pairs, and cannot add a new link to an archived
guest. Derived statistics are always recomputed and client-supplied statistic
fields are ignored.

Application code can roll back while revision `0009` remains applied. An
Alembic downgrade to `0008` drops both guest tables and all Guest Bank data, so
it requires a verified backup and explicit approval for any environment where
guest data must be recoverable.
