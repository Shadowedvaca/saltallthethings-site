# Phase 1 — FastAPI App Scaffold + Postgres Schema

## Goal
Stand up the SATT backend application structure, define the Postgres schema, wire in
sv_common auth, and run a one-time data migration from Cloudflare KV into Postgres.
Nothing connects to the frontend yet. The live site on GitHub Pages is untouched.

## Deliverables
- [ ] `src/satt/` app exists and imports cleanly
- [ ] Alembic migrations run clean against the `satt` Postgres schema
- [ ] `/health` endpoint returns `{status: "ok"}`
- [ ] `sv_common.auth` wired in — users table seeded, invite code support active
- [ ] Data migration script runs clean: Cloudflare KV → Postgres
- [ ] `pytest` passes

---

## Repo Structure to Create

saltallthethings-site/ └── src/ ├── sv_common/ ← copied from PullAllTheThings-site/src/sv_common/ (do not modify) └── satt/ ├── init.py ├── main.py ← FastAPI app entry point ├── config.py ← settings (env vars, DB URL, etc.) ├── database.py ← SQLAlchemy engine + session ├── models.py ← ORM models for satt.* schema ├── routes/ │ ├── init.py │ └── health.py ├── migrations/ │ ├── env.py │ ├── script.py.mako │ └── versions/ │ └── 0001_initial_satt_schema.py └── scripts/ └── migrate_from_cloudflare.py


---

## Server Context

- **Server:** Hetzner, IP `5.78.114.224`
- **Deploy path:** `/opt/satt-platform/`
- **PYTHONPATH:** `/opt/satt-platform/src`
- **Systemd unit name:** `satt`
- **Port:** `8200` (8100 is taken by PATT)
- **Staging URL:** `salt.shadowedvaca.com`
- **Database:** Existing Postgres instance on the server. Schema prefix: `satt`
- **Shared package:** `sv_common` is copied into `src/sv_common/` from the PATT repo.
  It is NOT installed via pip. It is found via PYTHONPATH. Do not modify sv_common files.

---

## Postgres Schema

All tables live in the `satt` schema (`CREATE SCHEMA IF NOT EXISTS satt`).

### satt.users
Managed entirely by `sv_common.auth`. Do not create this table manually — let
sv_common's Alembic migration handle it, scoped to the `satt` schema.

### satt.config
Single-row table. The entire config blob is stored as JSONB.

```sql
CREATE TABLE satt.config (
    id         INTEGER PRIMARY KEY DEFAULT 1,
    data       JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT single_row CHECK (id = 1)
);
Shape of data JSONB (must match current frontend defaults exactly):

{
  "aiModel": "claude",
  "claudeApiKey": "",
  "claudeModelId": "claude-sonnet-4-5-20250929",
  "openaiApiKey": "",
  "openaiModelId": "gpt-4o",
  "titleCount": 3,
  "jokeCount": 5,
  "youtubeVideo1": "",
  "youtubeVideo2": "",
  "youtubeVideo3": "",
  "showContext": "<default show context prompt>",
  "jokeContext": "<default joke context prompt>",
  "segments": [
    {"id": "opening",  "name": "Opening Hook / Intro",                      "description": "Set the tone, tease the episode topics"},
    {"id": "listener", "name": "Listener Corner",                            "description": "Community questions, comments, shoutouts (future segment)"},
    {"id": "updates",  "name": "What are Rocket and Trog up to?",           "description": "Personal WoW updates, what they've been playing"},
    {"id": "housing",  "name": "Rocket's Housing Update",                   "description": "Rocket's ongoing housing/life update segment"},
    {"id": "main",     "name": "Main Topic",                                "description": "The core discussion topic for the episode"},
    {"id": "salt",     "name": "A Little Sprinkle of Salt for your week",   "description": "Salty takes, hot takes, complaints, rants"},
    {"id": "closing",  "name": "Wrap-Up / What's Next / Closing",           "description": "Preview next episode, calls to action, sign off"}
  ]
}
satt.ideas
One row per processed episode idea.

CREATE TABLE satt.ideas (
    id              TEXT PRIMARY KEY,         -- Date.now().toString(36) + random() from JS
    titles          JSONB NOT NULL DEFAULT '[]',   -- string[]
    selected_title  TEXT,
    summary         TEXT,
    outline         JSONB NOT NULL DEFAULT '[]',   -- [{segmentId, segmentName, talkingPoints[]}]
    status          TEXT NOT NULL DEFAULT 'draft', -- draft | scheduled | recorded | released
    image_file_id   TEXT,
    raw_notes       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
satt.jokes
One row per joke.

CREATE TABLE satt.jokes (
    id              TEXT PRIMARY KEY,
    text            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',  -- active | used | retired
    source          TEXT NOT NULL DEFAULT 'manual',  -- manual | ai
    used_by_idea_id TEXT REFERENCES satt.ideas(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
satt.show_slots
One row per weekly recording slot.

CREATE TABLE satt.show_slots (
    id                    TEXT PRIMARY KEY,   -- e.g. "slot_1"
    episode_number        TEXT NOT NULL,      -- e.g. "EP001"
    episode_num           INTEGER NOT NULL,
    record_date           DATE NOT NULL,
    release_date          DATE NOT NULL,
    is_rollout            BOOLEAN NOT NULL DEFAULT false,
    release_date_override DATE
);
satt.assignments
Maps a show slot to an idea. One assignment per slot.

CREATE TABLE satt.assignments (
    slot_id     TEXT PRIMARY KEY REFERENCES satt.show_slots(id) ON DELETE CASCADE,
    idea_id     TEXT NOT NULL REFERENCES satt.ideas(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
sv_common.auth Integration
Wire auth identically to how PATT does it. Key points:

Users are stored in satt.users (sv_common scoped to the satt schema)
JWT tokens, bcrypt password hashing, invite code flow — all from sv_common
After migration, create the initial admin user (Mike/Trog) via the admin utility
Rocket gets an invite code — generated from the web UI (Phase 3), sent manually
Do not implement invite code generation UI in this phase. Just verify the auth infrastructure is working with a seeded admin user.

Data Migration Script
File: src/satt/scripts/migrate_from_cloudflare.py

This is a one-time script. Run it once after Phase 2 is deployed to production. It is safe to run in Phase 1 for local testing against a dev Postgres instance.

Usage: python migrate_from_cloudflare.py --api-url <worker_url> --password <admin_password>
Steps:

GET <api_url>/export with X-Auth: <password> header
Parse the 5 keys: config, ideas, jokes, showSlots, assignments
Insert into Postgres using SQLAlchemy — upsert on conflict (idempotent)
Print a summary: N ideas, N jokes, N slots, N assignments migrated
Do NOT delete from Cloudflare — leave Worker running until Phase 4 cutover
Shape mapping (JS camelCase → Postgres snake_case):

showSlots[].episodeNumber → show_slots.episode_number
showSlots[].recordDate → show_slots.record_date
showSlots[].releaseDate → show_slots.release_date
showSlots[].isRollout → show_slots.is_rollout
showSlots[].releaseDateOverride → show_slots.release_date_override
assignments is a {slotId: ideaId} map → insert as individual rows
ideas[].selectedTitle → ideas.selected_title
ideas[].imageFileId → ideas.image_file_id
Systemd Unit (for reference — do not deploy in this phase)
[Unit]
Description=Salt All The Things — FastAPI backend
After=network.target postgresql.service

[Service]
User=www-data
WorkingDirectory=/opt/satt-platform
Environment=PYTHONPATH=/opt/satt-platform/src
EnvironmentFile=/opt/satt-platform/.env
ExecStart=/opt/satt-platform/venv/bin/uvicorn satt.main:app --host 127.0.0.1 --port 8200
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
Environment Variables (.env)
DATABASE_URL=postgresql://user:password@localhost/sattdb
SECRET_KEY=<generate with: openssl rand -hex 32>
ENVIRONMENT=development
What NOT To Do In This Phase
Do not touch any frontend JS files
Do not configure Nginx
Do not implement any route beyond /health
Do not modify sv_common
Do not run the migration script against production Cloudflare KV yet (test against a local export file first)
Do not create the systemd unit yet
Definition of Done
Run these checks before marking Phase 1 complete:

# Schema exists
psql -c "\dn satt"

# Tables exist
psql -c "\dt satt.*"

# App starts
cd saltallthethings-site
PYTHONPATH=src uvicorn satt.main:app --port 8200
curl http://localhost:8200/health
# → {"status": "ok", "timestamp": "..."}

# Tests pass
PYTHONPATH=src pytest src/satt/tests/

# Migration script dry-run
python src/satt/scripts/migrate_from_cloudflare.py --dry-run