# Drive Folder Restructure — Overview

## What Is Changing

The Google Drive `Show Recordings` folder is being reorganised from four flat
type-folders into **one subfolder per episode**, named after the episode key.

### Old structure (flat, type-separated)
```
Show Recordings/
  Raw Dog Recordings/
    EP001_War-Within-Seasons-Ranked_2026-01-20.wav
  Finished Episodes/
    EP001_War-Within-Seasons-Ranked_2026-01-20.mp3
  Transcripts/
    EP001_War-Within-Seasons-Ranked_2026-01-20.txt
    EP001_War-Within-Seasons-Ranked_2026-01-20.json
  Cover Art/
    EP001_War-Within-Seasons-Ranked_2026-01-20.png
    EP001_War-Within-Seasons-Ranked_2026-01-20_artdirection.json
```

### New structure (episode subfolders)
```
Show Recordings/
  EP001_War-Within-Seasons-Ranked_2026-01-20/      ← folder name = key
    Raw_Dog_EP001_War-Within-Seasons-Ranked_2026-01-20.wav
    Trog_EP001_War-Within-Seasons-Ranked_2026-01-20.wav
    Rocket_EP001_War-Within-Seasons-Ranked_2026-01-20.wav
    EP001_War-Within-Seasons-Ranked_2026-01-20.mp3 ← no prefix
    Transcript_EP001_War-Within-Seasons-Ranked_2026-01-20.txt
    Transcript_EP001_War-Within-Seasons-Ranked_2026-01-20.json
    Cover_Art_EP001_War-Within-Seasons-Ranked_2026-01-20.png
    Art_Direction_EP001_War-Within-Seasons-Ranked_2026-01-20.json
```

**The `production_file_key` (e.g. `EP001_War-Within-Seasons-Ranked_2026-01-20`)
is unchanged — it now serves as both the subfolder name and the base of every
filename in that subfolder.**

---

## File Naming Convention Summary

| Type | Old name | New name |
|---|---|---|
| Combined raw recording | `{key}.wav` | `Raw_Dog_{key}.wav` |
| Trog individual track | *(none)* | `Trog_{key}.wav` |
| Rocket individual track | *(none)* | `Rocket_{key}.wav` |
| Finished episode | `{key}.mp3` | `{key}.mp3` *(unchanged)* |
| Transcript (text) | `{key}.txt` | `Transcript_{key}.txt` |
| Transcript (JSON) | `{key}.json` | `Transcript_{key}.json` |
| Cover art | `{key}.png` | `Cover_Art_{key}.png` |
| Art direction | `{key}_artdirection.json` | `Art_Direction_{key}.json` |

---

## Phases

| Phase | Document | What it covers |
|---|---|---|
| 1 | `restructure-phase-1-code.md` | All code changes needed before migration |
| 2 | `restructure-phase-2-migration.md` | Moving + renaming files in Drive |
| 3 | `restructure-phase-3-testing.md` | Testing and verification after migration |

---

## Execution Order and Dependency

**Phase 1 must be completed and deployed before Phase 2.**

The new code expects the new folder structure. The old code expects the old
structure. There is no bridge — the switchover is a maintenance window:

1. **Deploy Phase 1 code** — site scanning will be broken until migration completes.
2. **Run Phase 2 migration** — move files in Drive; update DB config key.
3. **Run scan** on Post-Production page to rebuild all asset inventories.
4. **Verify** per Phase 3 checklist.

Scanning will produce empty inventories during steps 1–2. That is expected and
harmless — no data is lost. Slot records and idea records are unaffected.

---

## Things That Do NOT Change

- `production_file_key` format — same slug pattern, same DB column
- Post-production page URL and UI layout (Trog/Rocket badges are additive)
- Episode numbering, slot records, idea records
- Auth, JWT, all non-Drive routes
- GitHub Actions deploy process
- The `sv_common` package (not touched)

---

## New Config Key

| Old key (removed) | New key |
|---|---|
| `gdriveFolderRawAudio` | `gdriveFolderShowRecordings` |
| `gdriveFolderFinishedAudio` | *(removed)* |
| `gdriveFolderTranscripts` | *(removed)* |
| `gdriveFolderCoverArt` | *(removed)* |

`gdriveFolderShowRecordings` is the Drive folder ID of the root
`Show Recordings` shared drive folder. The code finds the episode subfolder
by searching that root for a folder whose name matches `production_file_key`.
