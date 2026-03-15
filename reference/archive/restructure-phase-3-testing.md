# Drive Restructure — Phase 3: Testing & Verification

Run this after both Phase 1 (code deployed) and Phase 2 (files migrated) are
complete. Work through each section in order.

---

## 1. Config Page

- [ ] Load `config.html` and log in.
- [ ] Confirm only **one** Drive folder input is shown: "Show Recordings Folder ID".
- [ ] Confirm the saved folder ID is populated correctly (from the DB update in Phase 2).
- [ ] Save the page. Reload and confirm the value persists.
- [ ] Confirm the old fields (`Raw Audio Folder ID`, etc.) are **gone**.

---

## 2. Asset Scan — Single Episode

Pick one episode with a known complete set of files (raw + transcript + art + finished).

- [ ] Go to `postproduction.html`.
- [ ] Find the episode row. Click the file key cell to confirm the key matches
  the folder name you created in Drive.
- [ ] Click **Refresh Assets** (or use the single-episode scan if implemented).
- [ ] Confirm all asset badges update:
  - Raw = `ok`
  - Transcript = `ok`
  - Art Dir = `ok` (if art direction was generated)
  - Art = `ok` (if cover art exists)
  - Finished = `ok`
  - Trog = `ok` or `--` depending on whether `Trog_{key}.wav` exists
  - Rocket = `ok` or `--` depending on whether `Rocket_{key}.wav` exists

If any badge shows `--` when it should be `ok`, check:
1. The file name matches the convention exactly (case, underscores).
2. The file is in the correct episode subfolder (not still in the old flat folder).
3. The Drive sync is complete (watch the sync icon; large WAVs take time).

---

## 3. Asset Scan — All Episodes

- [ ] Click **Refresh Assets** to scan all eligible slots.
- [ ] Confirm no errors are returned in the toast notification.
- [ ] Check a few episodes at random to confirm inventories are populated.
- [ ] Confirm episodes with **no Drive folder yet** show all `--` badges (not errors).

---

## 4. Art Direction Generation

Pick an episode that has a transcript but no art direction yet.

- [ ] Click **Generate Art Direction** for that episode.
- [ ] Confirm the art direction panel appears with archetype, scene, etc.
- [ ] In Drive, confirm a file named `Art_Direction_{key}.json` exists in the
  episode subfolder (NOT in the old `Cover Art` folder).
- [ ] Click **Refresh Assets** for that slot.
- [ ] Confirm the Art Dir badge changes to `ok`.
- [ ] Click **Open Art Direction** (after dismissing the panel) to confirm the
  file is readable from Drive.

---

## 5. Cover Art / Episode Art Generation

Pick an episode where you want to generate art.

- [ ] Open the art direction panel.
- [ ] Click **Generate Art** (or **Regenerate Art**).
- [ ] Confirm the preview image appears.
- [ ] In Drive, confirm a file named `Cover_Art_{key}.png` exists in the
  episode subfolder (NOT in the old `Cover Art` folder).
- [ ] Click **Refresh Assets** for that slot.
- [ ] Confirm the Art badge changes to `ok`.

---

## 6. Episode Art Re-generation (delete + re-upload)

- [ ] Generate art a second time for the same episode.
- [ ] Confirm the old `Cover_Art_{key}.png` is deleted from Drive and a new one
  is uploaded. (Check via the Drive web UI or Drive for Desktop.)
- [ ] Confirm only one `Cover_Art_` file exists in the episode folder.

---

## 7. Local Watcher — New File Detection

On the recording PC (with `watch.py` running):

**Raw recording test:**
- [ ] Copy or create a small `.wav` file named `Raw_Dog_TEST_2099-01-01.wav`
  into `Show Recordings/TEST_2099-01-01/`.
- [ ] Confirm `watch.py` detects it (log output should appear within the settle
  delay of ~30 seconds).
- [ ] Confirm transcription is triggered automatically.
- [ ] Confirm output files appear in the same folder as the WAV:
  - `Transcript_TEST_2099-01-01.json`
  - `Transcript_TEST_2099-01-01.txt`
- [ ] Delete the test files when done.

**MP3 (finished episode) test:**
- [ ] Copy a small `.mp3` named `TEST_2099-01-01.mp3` into the same episode folder.
- [ ] Confirm `watch.py` detects it and triggers transcription.
- [ ] Confirm `Transcript_TEST_2099-01-01.txt/json` appears in the episode folder.
- [ ] Delete test files when done.

**Non-triggering files (should NOT trigger transcription):**
- [ ] Drop a `.wav` file that does NOT start with `Raw_Dog_` (e.g., `Trog_TEST.wav`).
- [ ] Confirm `watch.py` does NOT trigger transcription for it.

---

## 8. Transcription Output Paths

After triggering transcription via the watcher:

- [ ] Confirm the JSON and TXT files are in the episode subfolder, NOT in the
  old `Transcripts/` folder.
- [ ] Confirm the files are named `Transcript_{key}.txt` and `Transcript_{key}.json`,
  NOT the raw WhisperX output name (which would be `Raw_Dog_{key}.json`).

---

## 9. Server Notification After Transcription

If the watcher calls `--notify-server` after transcription:

- [ ] Check `journalctl -u satt -f` on the server during a transcription run.
- [ ] Confirm `POST /api/postproduction/scan` is received and returns 200.
- [ ] Confirm the episode's Transcript badge updates to `ok` on the post-production page after reload.

---

## 10. Public Episode List

The public episode index (`index.html`) uses `imageFileId` from the Idea row
(not from Drive directly). This is not affected by the restructure unless you
were previously reading cover art from the old Drive path.

- [ ] Load `https://saltallthethings.com` and confirm episode cards still display
  correctly.
- [ ] Confirm cover art thumbnails still load (they use `idea.image_file_id`,
  which is set when art is generated and should be unchanged).

---

## 11. Edge Cases to Watch For

| Scenario | Expected behaviour |
|---|---|
| Episode has no Drive folder yet | All badges show `--` (not an error) |
| Episode folder exists but is empty | All badges show `--` |
| Two files match same prefix + ext in one folder | Badge shows `conflict` |
| Drive sync still in progress | May show `--` temporarily; re-scan after sync |
| `production_file_key` not set for a slot | Badges show `n/a` (unchanged) |

---

## 12. Clean Up Old Folders

Once all verifications pass:

- [ ] Confirm the old flat folders are empty (or contain only unrecognised files).
- [ ] Delete (or archive to `_archive/`) in Drive:
  - `Raw Dog Recordings/`
  - `Finished Episodes/`
  - `Transcripts/`
  - `Cover Art/`
- [ ] Run a final **Refresh Assets** scan and confirm nothing breaks.

---

## Known Non-Issues

- **Existing `asset_inventory` rows** in the DB will show stale data until the
  next scan. Running Refresh Assets clears this.
- **The `artLog` in `satt.config`** stores art direction JSON inline — it is not
  affected by the file location change.
- **The `referenceImageFileIds`** config field references Drive file IDs for
  reference images fed into the AI — these IDs remain valid regardless of where
  the file lives in Drive.
