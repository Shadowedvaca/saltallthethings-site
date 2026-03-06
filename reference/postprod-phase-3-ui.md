# Post-Production Phase 3 — Post-Production Tab UI

## Goal

Build the post-production tab as a new auth-gated page. Shows the recorded-episode
queue with asset status columns. Lets the user set/edit the `production_file_key`,
trigger a Drive scan, and see at a glance what each episode still needs.

This is frontend-only (HTML/CSS/JS). No new backend routes beyond what Phase 1 and 2
delivered.

---

## Context

Read before starting:
- `reference/postprod-phase-1-schema.md` — API shape, nextStep logic
- `reference/postprod-phase-2-gdrive.md` — scan endpoint
- `CLAUDE.md` — frontend conventions (no build step, raw HTML/CSS/JS, camelCase API contract)

Existing pages to use as reference for patterns:
- `show_management.html` — auth gate, toast pattern, API calls
- `config.html` — inline editing pattern, save feedback
- `js/auth.js` — JWT session gate
- `js/storage.js` — API call helpers
- `js/toast.js` — toast notifications

---

## New File: `postproduction.html`

Auth-gated page. Add to the site nav alongside `show_management.html`, `jokes.html`,
`config.html`.

### Page structure

```
Header / Nav (same as other pages)

[Post-Production]                              [Refresh Assets]

Episode queue table:

| Ep    | Title                  | Record Date | File Key              | Raw   | Transcript | Art   | Finished | Next Step        |
|-------|------------------------|-------------|----------------------|-------|------------|-------|----------|------------------|
| EP003 | War Within S2 Ranked   | 2026-03-04  | EP003_..._2026-03-04 |  ok   |   stale    |  --   |    --    | Re-transcribe    |
| EP002 | Midnight Rising        | 2026-02-25  | EP002_..._2026-02-25 |  ok   |    ok      |  ok   |    ok    | Complete         |
| EP001 | War Within S1 Launch   | 2026-01-20  | [not set]            |  --   |    --      |  --   |    --    | Set file key     |
```

Sorted by record_date descending. Older incomplete episodes stay visible.

### Column details

**Ep** — `episodeNumber` from the slot

**Title** — `selectedTitle` from the idea (or italic "No title assigned" if null)

**Record Date** — formatted date

**File Key** — inline editable text field showing `productionFileKey`. Shows placeholder
"Click to set" if null. On blur/enter, calls `PUT /api/postproduction/{slotId}/key`,
then triggers a single-slot scan (`POST /api/postproduction/{slotId}/scan`), then
refreshes the row.

**Asset columns** (Raw, Transcript, Art, Finished) — badge indicators:

| State | Badge | Color |
|-------|-------|-------|
| present + current | ok | green |
| stale (audio newer than transcript) | stale | yellow |
| conflict (multiple matches) | conflict | orange |
| missing | -- | grey |
| no key set | n/a | grey |

**Next Step** — computed `nextStep` value from the API, rendered as a human-readable
label:

| nextStep value | Display |
|----------------|---------|
| `set_key` | Set file key |
| `upload_raw` | Upload raw audio |
| `transcribe` | Run transcription |
| `retranscribe` | Re-transcribe (stale) |
| `generate_art` | Generate art |
| `awaiting_editor` | Awaiting editor |
| `complete` | Complete |

"Complete" rows can optionally be collapsed/hidden via a "Show complete" toggle.

---

## Refresh Button

"Refresh Assets" button in the page header triggers `POST /api/postproduction/scan`
(all slots). Shows a spinner while running. On completion, reloads the queue data and
re-renders the table. Shows a toast: "Scanned N episodes."

If the server returns a 400 (folder IDs not configured), show a toast with a link to
the Config page.

---

## File Key Editing

Clicking the file key cell makes it an editable `<input>`. On Enter or blur:
1. Call `PUT /api/postproduction/{slotId}/key` with the new value
2. Call `POST /api/postproduction/{slotId}/scan` immediately after
3. Update the row in place with fresh asset data
4. Show toast: "Key updated and assets scanned."

If the key already has a value and the user clears it and saves empty, treat as null
(removes the key). Prompt for confirmation before clearing.

---

## JavaScript

New file: `js/postproduction.js`

Responsibilities:
- On page load: fetch `GET /api/postproduction`, render the table
- Handle "Refresh Assets" button
- Handle inline key editing
- Render asset badge states
- Compute display labels from `nextStep` values

Follow the same patterns as the existing JS modules:
- Use `fetch` with `Authorization: Bearer` from `auth.js`
- Use `toast.js` for feedback
- No framework, no bundler

---

## Nav Link

Add "Post-Production" to the navigation in all auth-gated pages:
- `show_management.html`
- `jokes.html`
- `config.html`
- `postproduction.html` itself

---

## Deliverables Checklist

- [ ] `postproduction.html` created and auth-gated
- [ ] Queue table renders correctly from `GET /api/postproduction`
- [ ] Asset badge states display correctly for all states (ok, stale, conflict, missing, n/a)
- [ ] `nextStep` column shows correct human-readable label
- [ ] "Refresh Assets" button calls scan endpoint and re-renders
- [ ] Inline file key editing works (update + scan + row refresh)
- [ ] Clearing a key shows a confirmation prompt
- [ ] Toast feedback on all actions
- [ ] 400 (not configured) shows actionable error toast
- [ ] "Show complete" toggle works
- [ ] Nav link added to all auth-gated pages
- [ ] `js/postproduction.js` follows existing JS module conventions

---

## What This Phase Does NOT Include

- Transcription automation (Phase 4)
- Art direction or image generation (Phases 5-6)
- Any action buttons for running transcription from the browser (that is a local
  machine operation — Phase 4 handles it via the watcher)
