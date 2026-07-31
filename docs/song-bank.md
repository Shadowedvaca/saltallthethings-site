# Song Bank data contract

The Song Bank is authenticated preparation data. It is independent of the Joke
Bank and stores one manually curated song per record.

## Browser contract

Each song uses this camelCase shape:

```json
{
  "id": "opaque-client-id",
  "artist": "Artist",
  "title": "Song title",
  "youtubeUrl": "https://youtu.be/video-id",
  "privateNotes": "Host preparation notes",
  "status": "unused",
  "assignedIdeaId": null,
  "createdAt": "server timestamp",
  "updatedAt": "server timestamp"
}
```

`artist`, `title`, and `youtubeUrl` are required. URLs are checked locally and
must be official HTTPS YouTube watch, short, live, embed, or `youtu.be` video
links. Validation never fetches YouTube content or metadata. `privateNotes` is
authenticated preparation data and is not included in public episode routes.

## Lifecycle and assignment

- `unused`: available and unassigned.
- `used`: assigned to exactly one existing idea.
- `retired`: unavailable and unassigned.

Assigning a song atomically frees any other song on the destination idea and
moves the selected song from any prior idea. Freeing a song returns it to
`unused`. Retiring or deleting a song removes its assignment. Deleting an idea,
including through a full idea-array replacement, frees its song in the same
transaction. Database uniqueness and lifecycle checks enforce at most one song
per idea and keep unassigned states free of stale idea IDs.

All mutations require the current `If-Match` data revision. A stale client
receives a conflict and cannot overwrite newer state.

## Authenticated management page

Hosts manage the bank at `songs.html`. The page supports manual creation,
search, lifecycle filtering, editing, retirement/restoration, assignment
removal, and deletion. It displays the assigned idea and scheduled episode
when available, but remains an authenticated preparation surface and never
publishes private talking points.

Artist, title, and YouTube link errors are shown before saving. The server
remains authoritative and the shared storage layer guards every mutation with
the current revision. If another session wins a write, the page restores the
latest server state and tells the host to review and retry. Retirement,
assignment removal, and deletion require confirmation because they remove data
or change episode assignment state. Navigation, form labels, live status/error
messages, filter state, and responsive layouts support keyboard and narrow-
screen use.

## Episode assignment and preparation

Processed and scheduled ideas in `show_management.html` list only `unused`
songs as assignment choices. An assigned song shows its artist, title, validated
YouTube link, and private talking points. Hosts can replace it with another
unused song or remove it from the episode; both actions use the atomic Song
lifecycle endpoints, and replacement/removal requires confirmation.

The full-screen authenticated show display repeats the assigned song and its
private talking points alongside the existing joke, summary, and outline. No
song data is copied into the idea record, and private notes remain absent from
public episode responses. Retired songs and songs used by another idea are not
offered. If another session changes or deletes a choice, revision conflict
handling reloads the current server state and the episode view reports that the
requested change was not applied.

## Import, export, and rollback

Authenticated export includes `songs`; browser import accepts it as an optional
array. Backups created before Song Bank support remain valid: omitting `songs`
leaves the current bank unchanged.

Alembic revision `0007` creates `satt.songs`. Downgrading to `0006` drops only
that table and permanently removes its records, so operators must export or
back up Song Bank data before downgrade once records exist. Application rollback
without migration downgrade preserves the table for a later compatible deploy.
