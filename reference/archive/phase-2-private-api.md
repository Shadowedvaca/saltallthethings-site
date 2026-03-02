# Phase 2 — Private API Endpoints

## Goal
Implement all authenticated API endpoints in FastAPI that replace the Cloudflare Worker.
By the end of this phase, the Worker is functionally redundant — every route it serves
exists on the Hetzner backend. The frontend is still untouched; the Worker stays live
until Phase 4 cutover.

## Deliverables
- [ ] All 5 authenticated CRUD endpoints implemented and tested
- [ ] Auth middleware wired — JWT from `sv_common.auth` on all private routes
- [ ] `X-Auth` bridge header supported temporarily (for Phase 3 transition testing)
- [ ] Public endpoints implemented (`/public/episodes`, `/public/homepage`)
- [ ] Response shapes match Cloudflare Worker exactly (frontend must not need changes yet)
- [ ] `pytest` passes for all new routes
- [ ] Manually verified: export all data, modify one key, re-export, confirm change

---

## Repo Structure to Add

```
src/satt/
├── routes/
│   ├── __init__.py
│   ├── health.py         ← already exists from Phase 1
│   ├── data.py           ← private CRUD routes
│   └── public.py         ← unauthenticated public routes
├── auth_bridge.py        ← temporary X-Auth → JWT bridge (delete in Phase 4)
├── crud.py               ← database read/write helpers
└── serializers.py        ← Postgres rows → JS-shaped JSON (snake_case → camelCase)
```

---

## Server Context

- **Port:** `8200`
- **Staging URL:** `salt.shadowedvaca.com`
- **PYTHONPATH:** `/opt/satt-platform/src`
- **Shared package:** `sv_common` in `src/sv_common/` — do not modify
- **Auth:** `sv_common.auth` — JWT in `Authorization: Bearer <token>` header
- **Bridge:** `X-Auth: <plaintext_password>` header also accepted in this phase only
- **Database:** Postgres, `satt.*` schema (created in Phase 1)

---

## Critical: Response Shape Contract

The frontend `storage.js` calls the Worker today. In Phase 3 we rewrite `storage.js`.
In this phase, **all responses must match the Worker's exact JSON shape** so we can
test Phase 2 independently before touching the frontend.

This means all JSON keys returned must be **camelCase** matching the current JS data
model. Use `serializers.py` to handle the snake_case → camelCase conversion from
Postgres.

### Serializer shapes required

**idea:**
```json
{
  "id": "abc123",
  "titles": ["Title A", "Title B"],
  "selectedTitle": "Title A",
  "summary": "...",
  "outline": [{"segmentId": "opening", "segmentName": "...", "talkingPoints": ["..."]}],
  "status": "draft",
  "imageFileId": null,
  "rawNotes": null,
  "createdAt": "2026-01-20T00:00:00Z",
  "updatedAt": "2026-01-20T00:00:00Z"
}
```

**joke:**
```json
{
  "id": "xyz789",
  "text": "Why did the WoW player...",
  "status": "active",
  "source": "ai",
  "usedByIdeaId": null,
  "createdAt": "2026-01-20T00:00:00Z"
}
```

**showSlot:**
```json
{
  "id": "slot_1",
  "episodeNumber": "EP001",
  "episodeNum": 1,
  "recordDate": "2026-01-20",
  "releaseDate": "2026-03-03",
  "isRollout": true,
  "releaseDateOverride": null
}
```

**assignments** (returned as a flat map, not an array):
```json
{
  "slot_1": "ideaId_abc",
  "slot_2": "ideaId_xyz"
}
```

**config:** returned as-is from the JSONB `data` column — no transformation needed.

---

## Routes to Implement

### Auth Middleware

All private routes require a valid JWT **or** a valid `X-Auth` plaintext password
(bridge, temporary). Use a FastAPI dependency:

```python
async def require_auth(
    authorization: str = Header(None),
    x_auth: str = Header(None, alias="X-Auth")
):
    # 1. Try JWT from Authorization: Bearer <token>
    # 2. Fall back to X-Auth plaintext password bridge
    # 3. Raise 401 if neither valid
```

The X-Auth bridge checks the plaintext password against `bcrypt` hash stored in env
(`ADMIN_PASSWORD_HASH`). This is a temporary measure — removed in Phase 4.

---

### GET /health
Already implemented in Phase 1. No changes.

---

### GET /export
Returns all 5 data types in a single response. This is what `storage.js` calls on
`init()`.

**Auth:** Required

**Response:**
```json
{
  "config": { ...config JSONB data... },
  "ideas": [ ...idea objects... ],
  "jokes": [ ...joke objects... ],
  "showSlots": [ ...showSlot objects... ],
  "assignments": { "slot_1": "ideaId_abc", ... }
}
```

Implementation note: this is the hot path — called on every page load. Keep it fast.
Single query per table, no N+1.

---

### GET /data/:key
Read one key. `key` must be one of: `config`, `ideas`, `jokes`, `showSlots`,
`assignments`.

**Auth:** Required

**Response:** The serialized value for that key (same shape as in `/export`).

**Error:** `400` if key is not in the allowed set.

---

### PUT /data/:key
Overwrite one key entirely. This is how the frontend saves changes — it always sends
the full array/object, never a partial update.

**Auth:** Required

**Request body:** The full new value for the key.

**Behavior per key:**
- `config` — upsert the single config row (replace `data` JSONB entirely)
- `ideas` — replace all rows: delete existing, bulk insert new. Preserve `created_at`
  if an idea with the same `id` already exists.
- `jokes` — same pattern as ideas
- `showSlots` — same pattern
- `assignments` — delete all existing rows, insert from the `{slotId: ideaId}` map

**Response:** `{"ok": true}`

**Important:** The frontend sends the entire array on every write. Do not attempt
partial/diff updates. Match the Worker behavior exactly.

---

### PUT /import
Bulk write all 5 keys at once. Same as calling `PUT /data/:key` for each key.
Used for the import feature in `config.html`.

**Auth:** Required

**Request body:**
```json
{
  "config": {...},
  "ideas": [...],
  "jokes": [...],
  "showSlots": [...],
  "assignments": {...}
}
```

**Response:** `{"ok": true}`

---

### GET /public/episodes
Unauthenticated. Returns released episodes for the public site.

**Auth:** None

**Query params:**
- `page` (int, default 1)
- `limit` (int, default 20, max 50)

**Release gating:** Only return episodes where `releaseDate <= today` in PST.
Use `pytz.timezone('America/Los_Angeles')` — do NOT hardcode UTC-8. This is the
fix from the Worker's hardcoded UTC-8.

**Logic:**
1. Get all assignments (slot_id → idea_id)
2. Join with show_slots — filter where effective release date <= today PST
   (effective = `release_date_override` if set, else `release_date`)
3. Join with ideas — get selected_title and summary
4. Sort by release date descending
5. Paginate

**Response:**
```json
{
  "episodes": [
    {
      "episodeNumber": "EP001",
      "title": "Selected title string",
      "summary": "Episode summary...",
      "releaseDate": "2026-03-03"
    }
  ],
  "page": 1,
  "limit": 20,
  "total": 42
}
```

**Cache headers:** `Cache-Control: public, max-age=300` (5 minutes, matching Worker)

---

### GET /public/homepage
Unauthenticated. Returns YouTube video IDs for the hero section.

**Auth:** None

**Response:**
```json
{
  "youtubeVideo1": "abc123",
  "youtubeVideo2": "def456",
  "youtubeVideo3": "ghi789"
}
```

**Cache headers:** `Cache-Control: public, max-age=300`

---

## CRUD Helpers (crud.py)

Implement these functions — routes should call crud, not query the DB directly:

```python
# Config
async def get_config(db) -> dict
async def save_config(db, data: dict) -> None

# Ideas
async def get_ideas(db) -> list[dict]
async def replace_ideas(db, ideas: list[dict]) -> None

# Jokes
async def get_jokes(db) -> list[dict]
async def replace_jokes(db, jokes: list[dict]) -> None

# Show Slots
async def get_show_slots(db) -> list[dict]
async def replace_show_slots(db, slots: list[dict]) -> None

# Assignments
async def get_assignments(db) -> dict  # {slotId: ideaId}
async def replace_assignments(db, assignments: dict) -> None

# Public
async def get_released_episodes(db, page: int, limit: int) -> dict
async def get_homepage_config(db) -> dict
```

---

## Tests to Write

```
src/satt/tests/
├── test_health.py          ← already exists
├── test_auth.py            ← JWT valid/invalid, X-Auth valid/invalid, 401 cases
├── test_export.py          ← export returns all 5 keys with correct shapes
├── test_data_crud.py       ← GET and PUT for each of the 5 keys
├── test_import.py          ← bulk import round-trip
├── test_public_episodes.py ← release gating, pagination, PST timezone
└── test_public_homepage.py ← returns video IDs from config
```

Use `pytest` with `httpx.AsyncClient`. Seed a test Postgres schema (`satt_test`)
for isolation — do not run tests against the production schema.

---

## What NOT To Do In This Phase

- Do not touch any frontend JS or HTML files
- Do not configure Nginx or systemd
- Do not implement AI proxy endpoints (that is Phase 3)
- Do not implement invite code generation UI (that is Phase 3)
- Do not remove the X-Auth bridge (that is Phase 4)
- Do not turn off the Cloudflare Worker
- Do not run the migration script against production yet

---

## Definition of Done

```bash
# All tests pass
PYTHONPATH=src pytest src/satt/tests/ -v

# Export round-trip
curl -H "Authorization: Bearer <token>" http://localhost:8200/export
# → all 5 keys present, correct shapes

# X-Auth bridge works
curl -H "X-Auth: <plaintext_password>" http://localhost:8200/export
# → same response

# Public endpoints work unauthenticated
curl http://localhost:8200/public/episodes
curl http://localhost:8200/public/homepage

# PUT /data/jokes round-trip
curl -X PUT -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '[{"id":"test1","text":"Why so salty?","status":"active","source":"manual","usedByIdeaId":null,"createdAt":"2026-01-01T00:00:00Z"}]' \
  http://localhost:8200/data/jokes

curl -H "Authorization: Bearer <token>" http://localhost:8200/data/jokes
# → array with the joke you just wrote

# 401 on missing auth
curl http://localhost:8200/export
# → 401