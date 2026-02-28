# CLAUDE.md — Salt All The Things

This file is the primary context document for Claude Code sessions on this project.
Read it fully before doing any work.

---

## Project Overview

**Salt All The Things** is a World of Warcraft podcast site at `saltallthethings.com`.
Two hosts: Rocket (primary host) and Trog (co-host, technical).

This repo contains both the static frontend and the FastAPI backend.

---

## Repository Structure

```
saltallthethings-site/
├── CLAUDE.md                   ← you are here
├── .github/
│   └── workflows/
│       └── deploy.yml          ← deploys static files to Hetzner (no build step)
├── references/                 ← migration phase docs (read-only reference)
├── src/
│   ├── sv_common/              ← shared auth/services package (DO NOT MODIFY)
│   └── satt/                   ← FastAPI application
│       ├── __init__.py
│       ├── main.py             ← FastAPI app entry point
│       ├── config.py           ← settings (env vars)
│       ├── database.py         ← SQLAlchemy engine + session
│       ├── models.py           ← ORM models
│       ├── crud.py             ← database read/write helpers
│       ├── serializers.py      ← snake_case → camelCase for JS contract
│       ├── prompts.py          ← AI prompt construction
│       ├── ai_client.py        ← httpx calls to Anthropic/OpenAI
│       ├── routes/
│       │   ├── health.py
│       │   ├── data.py         ← private CRUD routes
│       │   ├── ai.py           ← AI proxy endpoints
│       │   └── public.py       ← unauthenticated public routes
│       ├── migrations/
│       │   ├── env.py
│       │   ├── script.py.mako
│       │   └── versions/
│       └── tests/
├── css/
│   └── style.css
├── js/
│   ├── auth.js                 ← JWT login flow
│   ├── storage.js              ← API-backed cache (talks to FastAPI)
│   ├── ai-service.js           ← calls FastAPI AI proxy
│   ├── show-engine.js          ← pure date math, no API calls
│   ├── site-config.js          ← platform links, show metadata
│   └── toast.js                ← toast notifications
├── images/
├── index.html                  ← public landing page (no auth)
├── show_management.html        ← auth-gated: ideas + schedule board
├── jokes.html                  ← auth-gated: joke bank
├── config.html                 ← auth-gated: settings + invite codes
└── register.html               ← public: invite code registration
```

---

## Server Infrastructure

- **Host:** Hetzner VPS, IP `5.78.114.224`
- **Deploy path:** `/opt/satt-platform/`
- **Static files:** `/opt/satt-platform/static/`
- **PYTHONPATH:** `/opt/satt-platform/src`
- **Systemd unit:** `satt` (port `8200`, internal only)
- **Nginx:** Reverse proxies `/api/` and `/public/` to port `8200`, serves static
  files directly from `/opt/satt-platform/static/`
- **SSL:** Certbot / Let's Encrypt
- **Production URL:** `https://saltallthethings.com`
- **Staging URL:** `https://salt.shadowedvaca.com`

### Other sites on this server

| Domain | Project | Port | Systemd unit |
|---|---|---|---|
| `shadowedvaca.com` | Meandering Muck | `8000` | `shadowedvaca` |
| `pullallthethings.com` | Pull All The Things | `8100` | `patt` |
| `saltallthethings.com` | Salt All The Things | `8200` | `satt` |

Do not touch configs, units, or files belonging to other sites.

---

## Python Stack

- **Framework:** FastAPI + Uvicorn
- **ORM:** SQLAlchemy (async)
- **Migrations:** Alembic
- **HTTP client:** httpx (async) — used for AI proxy calls
- **Auth:** `sv_common.auth` — JWT, bcrypt, invite codes
- **Testing:** pytest + httpx.AsyncClient
- **Python version:** match whatever PATT uses on this server

### sv_common

`sv_common` is a shared services package copied from `PullAllTheThings-site/src/sv_common/`.
It is found via `PYTHONPATH` — not installed via pip.

**Do not modify any file in `src/sv_common/`.** If you need a change to sv_common,
flag it for the developer. Changes must be made in the PATT repo first, then
manually propagated here.

---

## Database

- **Engine:** Postgres (existing instance on the server)
- **Schema:** `satt` — all tables are prefixed `satt.*`
- **Other schemas on this server:** `patt`, `common`, `guild_identity` — do not touch

### Tables

| Table | Purpose |
|---|---|
| `satt.users` | Managed by sv_common.auth |
| `satt.config` | Single-row JSONB blob — AI settings, prompts, YouTube IDs |
| `satt.ideas` | Processed episode ideas with titles, summary, outline |
| `satt.jokes` | Joke bank entries |
| `satt.show_slots` | Weekly recording/release schedule slots |
| `satt.assignments` | Maps slot_id → idea_id |

### Key data design decisions

1. **No UUIDs** — IDs are `Date.now().toString(36) + random()` generated by JS.
   Accept and store them as TEXT. Do not regenerate or reformat them server-side.
2. **Full replace on write** — `PUT /api/data/:key` always receives the full array
   and replaces all rows. No partial updates.
3. **assignments is a flat map** — `{slotId: ideaId}` in JSON, two-column table
   in Postgres.
4. **config is a single row** — JSONB `data` column, always upserted as a whole.
5. **camelCase contract** — all JSON returned to the frontend must use camelCase
   keys matching the original JS data model. `serializers.py` handles conversion.

---

## API Routes

### Private (JWT required)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/export` | All 5 data types as JSON (called on page load) |
| `GET` | `/api/data/:key` | Read one key |
| `PUT` | `/api/data/:key` | Overwrite one key (full replace) |
| `PUT` | `/api/import` | Bulk write all keys |
| `POST` | `/api/ai/process-idea` | Proxy idea processing to Anthropic/OpenAI |
| `POST` | `/api/ai/generate-jokes` | Proxy joke generation to Anthropic/OpenAI |
| `POST` | `/api/auth/invite` | Generate invite code (admin only) |

### Public (no auth)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/public/episodes` | Released episodes, paginated |
| `GET` | `/public/homepage` | YouTube video IDs for hero |
| `POST` | `/api/auth/login` | Exchange credentials for JWT |
| `POST` | `/api/auth/register` | Register with invite code |

### Auth notes
- JWT in `Authorization: Bearer <token>` header
- Token TTL: 8 hours
- Invite codes: one-time use, 48-hour expiry
- No X-Auth header support — that bridge was removed after Phase 4 cutover

---

## Frontend JS Modules

| File | Purpose | Talks to backend? |
|---|---|---|
| `auth.js` | JWT login gate, session management | Yes — `/api/auth/login` |
| `storage.js` | In-memory cache + async write-back | Yes — `/api/export`, `/api/data/:key` |
| `ai-service.js` | AI generation calls | Yes — `/api/ai/*` |
| `show-engine.js` | Weekly slot date math | No — pure computation |
| `site-config.js` | Platform links, show metadata | No — static config |
| `toast.js` | Toast notifications | No — UI only |

### Frontend conventions
- No build step — raw HTML/CSS/JS, no bundler, no framework
- `API_BASE = 'https://saltallthethings.com/api'` hardcoded in `storage.js`
  and `ai-service.js`
- AI keys are stored in `satt.config` in Postgres — never in the frontend
- `show-engine.js` is never modified — it is pure date logic and has no
  dependencies on auth or storage

---

## AI Proxy Design

AI calls (Anthropic / OpenAI) are proxied through FastAPI. The browser never
calls Anthropic or OpenAI directly.

- API keys live in `satt.config` in Postgres
- `ai_client.py` makes raw `httpx` calls — no Anthropic or OpenAI Python SDKs
- `prompts.py` builds system and user prompts — exact equivalents of the
  original JS prompt logic
- Model selection is runtime config (`config.aiModel`: `"claude"` or `"openai"`)

---

## Pages

| File | Auth | Purpose |
|---|---|---|
| `index.html` | No | Public landing — hero, YouTube videos, platform links |
| `show_management.html` | Yes | Ideas Workshop + drag-and-drop Schedule Board |
| `jokes.html` | Yes | Joke bank — AI generator + manual CRUD |
| `config.html` | Yes | AI settings, prompts, segments, YouTube IDs, invite codes |
| `register.html` | No | Invite code registration for new users |

---

## Deploy

Static files are deployed to `/opt/satt-platform/static/` via the GitHub Actions
workflow on push to `main`. There is no build step — files are copied as-is.

The FastAPI backend is deployed manually:
```bash
cd /opt/satt-platform
git pull
PYTHONPATH=src alembic upgrade head   # if there are schema changes
sudo systemctl restart satt
```

---

## Environment Variables

Stored in `/opt/satt-platform/.env`:

```
DATABASE_URL=postgresql://user:password@localhost/sattdb
SECRET_KEY=<hex string — generate with: openssl rand -hex 32>
ENVIRONMENT=production
AI_REQUEST_TIMEOUT=60
```

AI API keys are NOT in `.env` — they are stored in `satt.config` in Postgres
and managed through the Config page UI.

---

## Testing

```bash
# Run all tests
PYTHONPATH=src pytest src/satt/tests/ -v

# Run with coverage
PYTHONPATH=src pytest src/satt/tests/ --cov=satt --cov-report=term-missing
```

Tests use a separate `satt_test` Postgres schema. Never run tests against
the production schema.

AI proxy tests mock upstream calls with `respx` or `pytest-httpx` — no real
API calls in tests.

---

## Common Tasks

### Add a new API route
1. Create or update the appropriate file in `src/satt/routes/`
2. Register the router in `src/satt/main.py`
3. Add CRUD helpers to `src/satt/crud.py` if DB access needed
4. Write tests in `src/satt/tests/`

### Add a new database table
1. Add ORM model to `src/satt/models.py`
2. Generate migration: `PYTHONPATH=src alembic revision --autogenerate -m "description"`
3. Review generated migration in `src/satt/migrations/versions/`
4. Apply: `PYTHONPATH=src alembic upgrade head`

### Restart the service
```bash
sudo systemctl restart satt
sudo systemctl status satt
journalctl -u satt -f   # tail logs
```

### Check Nginx
```bash
sudo nginx -t
sudo systemctl reload nginx
```

### Check all three sites are up
```bash
curl -s -o /dev/null -w "%{http_code}" https://shadowedvaca.com
curl -s -o /dev/null -w "%{http_code}" https://pullallthethings.com
curl -s -o /dev/null -w "%{http_code}" https://saltallthethings.com
```

---

## What Not To Do

- **Do not modify `src/sv_common/`** — changes must come from the PATT repo
- **Do not touch other sites** — `shadowedvaca.com` and `pullallthethings.com`
  have their own configs and units; leave them alone
- **Do not expose port `8200` directly** — all traffic goes through Nginx
- **Do not store AI keys in `.env`** — they live in `satt.config` in Postgres
- **Do not use the Anthropic or OpenAI Python SDKs** — use raw httpx calls
- **Do not add a build step** — the frontend is plain HTML/CSS/JS, no bundler
- **Do not run tests against the production schema** — use `satt_test`