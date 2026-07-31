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

## Import, export, and rollback

Authenticated export includes `songs`; browser import accepts it as an optional
array. Backups created before Song Bank support remain valid: omitting `songs`
leaves the current bank unchanged.

Alembic revision `0007` creates `satt.songs`. Downgrading to `0006` drops only
that table and permanently removes its records, so operators must export or
back up Song Bank data before downgrade once records exist. Application rollback
without migration downgrade preserves the table for a later compatible deploy.
