# Salt All The Things — Podcast Website & Show Management

Website and internal production tools for the *Salt All The Things* WoW podcast.

**Production:** https://saltallthethings.com
**Staging:** https://salt.shadowedvaca.com

---

## Stack

- **Frontend:** Plain HTML/CSS/JS — no build step, no framework
- **Backend:** FastAPI + Uvicorn (Python), SQLAlchemy async, Alembic
- **Database:** Postgres (`satt` schema on shared Hetzner instance)
- **Auth:** JWT (8h TTL) + bcrypt, invite-code registration
- **AI:** Anthropic/OpenAI proxied through FastAPI — keys stored in DB, never in code
- **Host:** Hetzner VPS `5.78.114.224`, served by Nginx + Let's Encrypt

---

## Deploy

### Static files (automatic)

Push to `main` — GitHub Actions SSHes into the server, runs `git pull`, copies
static files to `/opt/satt-platform/static/`, and restarts the `satt` service.

Required GitHub secrets:
- `STAGING_SSH_KEY` — private key for `root@5.78.114.224`
- `STAGING_SSH_KNOWN_HOSTS` — server host fingerprint

### Backend (manual)

```bash
ssh hetzner
cd /opt/satt-platform
git pull
PYTHONPATH=src alembic upgrade head   # only if there are schema changes
sudo systemctl restart satt
```

---

## Local development

### Python backend

```bash
python -m venv venv
venv/Scripts/activate        # Windows
pip install -r requirements.txt

# Needs a local Postgres instance or tunnel to the server
cp .env.example .env         # fill in DATABASE_URL, SECRET_KEY
PYTHONPATH=src uvicorn satt.main:app --reload
```

### Frontend

Open the HTML files directly in a browser or serve them statically.
The JS hardcodes `https://saltallthethings.com/api` as the API base —
override in `js/storage.js` and `js/ai-service.js` if pointing at a local backend.

### Tests

```bash
PYTHONPATH=src pytest src/satt/tests/ -v
```

Tests use a separate `satt_test` Postgres schema. Never run against production.

---

## Pages

| Page | Auth | Purpose |
|---|---|---|
| `index.html` | No | Public landing — hero, YouTube embeds, platform links |
| `show_management.html` | Yes | Ideas workshop + drag-and-drop schedule board |
| `jokes.html` | Yes | Joke bank — AI generator + manual CRUD |
| `config.html` | Yes | AI settings, prompts, YouTube IDs, invite codes, user management |
| `register.html` | No | Invite-code registration for new users |
| `login.html` | No | JWT login gate (redirects to referrer after auth) |

---

## Environment variables

Stored in `/opt/satt-platform/.env` on the server:

```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/satt_db
SECRET_KEY=<hex string>
ENVIRONMENT=production
SITE_URL=https://saltallthethings.com
CORS_ORIGINS=https://saltallthethings.com,https://salt.shadowedvaca.com
AI_REQUEST_TIMEOUT=60
```

AI API keys are **not** in `.env` — they are stored in `satt.config` in Postgres
and managed through the Config page.

---

## Server management

```bash
# Service status / logs
sudo systemctl status satt
journalctl -u satt -f

# Nginx
sudo nginx -t
sudo systemctl reload nginx

# SSL certs (auto-renew via certbot timer)
sudo certbot renew --dry-run
```
