# ChatGPT-Answers.md — Post-Production Flow Context for Claude Code

These answers correspond to the questions in ChatGPT-Questions.md. They describe the
current state of the SATT codebase and data model so the Markdown spec can be written
against what actually exists, not assumptions.

---

## Show Records

**Q1. What is the exact entity for an episode/show in your app right now?**

There are two linked entities:

- `Idea` — the episode content (titles, summary, outline, raw notes, status). Lives in
  `satt.ideas`. This is what the host creates and plans.
- `ShowSlot` — the scheduling record (episode number, record date, release date). Lives
  in `satt.show_slots`.

They are joined by `Assignment` (`satt.assignments`), a two-column table: `slot_id →
idea_id`. One slot has zero or one idea assigned to it.

For the post-production flow, `ShowSlot` is the anchor — it holds the episode number
and dates. `Idea` holds the content. Both are needed to represent a complete episode.

**Q2. Where is the "recorded" state stored today?**

There is no explicit "recorded" flag or datetime in the current schema. The `Idea` model
has a `status` text field (default `'draft'`), but no `'recorded'` value is defined or
used today.

The practical proxy for "this episode has been recorded" is: `ShowSlot.record_date <=
today`. The post-production tab will use this as its filter. A proper `status` value or
boolean on `Idea` (e.g., `status = 'recorded'`) may be added as part of this work.

**Q3. Do you already store a record date separately from publish date?**

Yes. `ShowSlot` has two separate `Date` columns:

- `record_date` — the day the episode is recorded
- `release_date` — the public release/publish date (with an optional
  `release_date_override`)

---

## File Matching

**Q4. What is the current standard filename pattern?**

> The transcription scripts reference these folders but do not
> enforce a filename convention:
> - Raw recording: `J:\Shared drives\Salt All The Things\Show Recordings\Raw Dog Recordings\`
> - Finished episode: `J:\Shared drives\Salt All The Things\Show Recordings\Finished Episodes\`
> - Transcripts: `J:\Shared drives\Salt All The Things\Show Recordings\Transcripts\`
> - Album art: `J:\Shared drives\Salt All The Things\Show Recordings\Cover Art`
>

These folders are all in google drive.  I can provide IDs for each folder.  We should not be using local paths for this, we should be looking at google drive folders.  We currently use a Google Drive file ID pattern to attach art to the shows and display it on the web page.

> Please fill in the expected filename pattern, for example:
> - Raw: `EP001_War-Within-Seasons-Ranked_2026-01-20.wav`
> - Finished: `EP001_War-Within-Seasons-Ranked_2026-01-20.mp3`
> - Transcript: `EP001_War-Within-Seasons-Ranked_2026-01-20.txt` and `EP001_War-Within-Seasons-Ranked_2026-01-20.json`
> - Art: `EP001_War-Within-Seasons-Ranked_2026-01-20.png`

**Q5. Is there already a canonical episode slug in the DB?**

`ShowSlot.episode_number` is a text field that stores the episode number (e.g.,
`"EP042"` or `"Episode 42"` — exact format is up to the host). It is not currently used
for filename matching; that connection does not exist yet. `ShowSlot.episode_num` also
exists as an integer column.

There is no production file key or filename stub stored anywhere in the DB today.

**Q6. File matching approach?**

A single **canonical base filename stored on the episode record**, with all four asset
types resolving against it. Per the user: "I want to control the flow by it only
matching episodes built on a file name which is mostly standard but I need to be able to
manually rename if I want."

Automatic guessing (e.g., derived from `episode_number`) provides the default; manual
override replaces it.

**Q7. What should the field be called?**

Suggested name: `production_file_key` — a text field added to `ShowSlot` (or `Idea`,
but `ShowSlot` is the better anchor since it owns the dates). Example value: `SATT-EP042`.

All asset presence checks resolve as:
- Raw audio: `{RAW_DIR}/{production_file_key}.*`
- Finished audio: `{FINISHED_DIR}/{production_file_key}.*`
- Transcript: `{TRANSCRIPT_DIR}/{production_file_key}.txt`
- Album art: `{ART_DIR}/{production_file_key}.png` (or `.jpg`)

---

## Asset Storage

**Q8. Where do these files live today?**

Google Drive shared folder, synced to a local drive on the recording machine at
`J:\Shared drives\Salt All The Things\Show Recordings\`. Subfolders:
- `Raw Dog Recordings\` — glued raw recording, pre-editor
- `Finished Episodes\` — editor (Skate)'s cleaned output
- `Transcripts\` — WhisperX output (text files)
- Album art: location TBD — does not exist yet as a workflow

The files live on Google Drive. No files live on the Hetzner server. The Hetzner server
has 4GB RAM and is a shared host; no heavy processing or local file access happens there.

**Q9. Does the web app have filesystem visibility?**

No. The Hetzner server cannot see the Google Drive folders. The web app has no knowledge
of which files exist on the local machine.

The architecture for this feature requires a **local scan agent** (running on the
recording machine) that checks file presence and pushes a metadata inventory to the web
app via an API endpoint. The web app stores and displays that inventory; it does not
access files directly.

**Q10. For album art, what is currently stored?**

The `Idea` model has an `image_file_id` text column. It is **currently unused** — no
value is ever written to it today. No image generation workflow exists yet. The
post-production feature will be the first to define and populate this field, or a
replacement field with a clearer name.

---

## Transcript Flow

**Q11. Is there a DB field for transcript text or path?**

No. Transcripts are currently **files only** in the `Transcripts\` folder on Google
Drive. There is no transcript text, file path, or reference stored in the database
anywhere today.

**Q12. When a cleaned audio file replaces the raw-based transcript, what should happen?**

**Overwrite entirely.** Per the user: "I want to rerun the transcription on the cleaner
file and replace the old one." No versioning, no history. The transcript file on disk
is overwritten; the app's asset inventory is updated to reflect the new file.

---

## UI / Workflow

**Q13. Single post-production queue with asset columns?**

Yes. One row per episode. Columns:
- Episode (number + title if assigned)
- Record Date
- Raw Dog Recording (present / missing)
- Finished Show (present / missing)
- Transcript (present / missing / stale)
- Album Art (present / missing)
- Match Name (the `production_file_key`, editable inline)
- Status / Next Step

**Q14. Which episodes should appear?**

Episodes where `ShowSlot.record_date <= today` (recording date has arrived or passed).
This is the only current filter. No explicit "recorded" status flag exists yet; the date
is the proxy.

If a `status = 'recorded'` field is added to `Idea` or `ShowSlot` as part of this
feature, the filter can optionally require it too. But the date-based filter is the
minimum viable approach against the current schema.

**Q15. Do older unfinished episodes stay visible?**

Yes. An episode stays in the queue until all required assets are present and current.
Episodes are sorted descending by `record_date` (most recent first).

---

## Completion Logic

**Q16-17. What counts as "complete"?**

The process is that Rocket and I talk on Discord, we record wav files separately on our locals.  Then we upload both individual wav files to Google Drive.  I glue those files together and then load them to Raw Dog Recordings.

Then, I take the Raw Dog Recording and I transcribe it using my script process.

Then, I take the transcription and I use ChatGPT to produce album artwork.

Currently, our audio guy is not keeping up, so if he is not able to finish the episode in time, we are releasing these as raw.  If he does get to it in time, I want to be able to re-do the transcription, the art, and then load the mp3 to spotify.

**Q18. What should "needed" mean?**

All of the following:
- Missing required artifact (file does not exist for the `production_file_key`)
- Stale artifact (transcript exists but audio file is newer — already detected by
  `transcribe.bat`)
- Filename mismatch needing manual intervention (`production_file_key` not yet set, or
  set but no matching file found)

---

## Matching + Manual Control

**Q19. If multiple files match one episode, what should happen?**

Show a **conflict state** on that asset cell — flag it visually so the user can resolve
it. Do not auto-pick.

**Q20. Manual override actions?**

The primary action is **"Set base name"** — editing the `production_file_key` on the
episode record. All four asset types resolve from that one key, so fixing the key fixes
all four lookups at once.

Individual per-asset overrides (attach specific file paths) are a possible future
enhancement but not required for the initial build.

---

## Technical Integration Boundary

**Q21-22. What does the local machine do vs. what does the server do?**

**Local machine (recording PC):**
- Runs the folder watcher (Python `watchdog` or equivalent)
- Runs WhisperX + diarization + speaker labeling (RAM-intensive, cannot run on Hetzner)
- Scans the three asset folders for file presence and last-modified timestamps
- Pushes a JSON asset inventory to a new private API endpoint on the web app
- Triggers the auto-transcription pipeline when new files land

**Server (Hetzner / FastAPI):**
- Stores the `production_file_key` per episode in Postgres
- Stores the last-pushed asset inventory (file present/absent, last modified) in Postgres
  or as a JSONB blob on the episode record
- Serves the post-production tab UI and API
- Hosts the art-direction AI endpoints (text generation only — no image processing locally)
- Does NOT access the Google Drive folders directly, ever

The clean boundary: **local machine owns files, server owns metadata and UI.**

The local watcher script pushes to a new endpoint, e.g.:

```
POST /api/assets/inventory
{
  "episodes": [
    {
      "production_file_key": "SATT-EP042",
      "raw_audio": { "present": true, "modified": "2026-03-01T18:22:00Z" },
      "finished_audio": { "present": false },
      "transcript": { "present": true, "modified": "2026-03-01T19:05:00Z" },
      "album_art": { "present": false }
    }
  ]
}
```

The app stores this and the post-production tab reads from it. No live filesystem polling
from the browser or server.
