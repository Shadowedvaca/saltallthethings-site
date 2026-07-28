# Salt All The Things — Podcast Website & Show Management

Website and internal production tools for the *Salt All The Things* WoW podcast.

**Production:** https://saltallthethings.com

The Foundation milestone is establishing isolated development and test
environments. See `docs/delivery.md` for the authoritative rollout state and
approval gates.

---

## Stack

- **Frontend:** Plain HTML/CSS/JS — no build step, no framework
- **Backend:** FastAPI + Uvicorn (Python), SQLAlchemy async, Alembic
- **Database:** Postgres (`satt` schema on shared Hetzner instance)
- **Auth:** JWT (8h TTL) + bcrypt, invite-code registration
- **AI:** Anthropic/OpenAI proxied through FastAPI — keys stored in DB, never in code
- **Host:** Hetzner VPS `5.78.114.224`, served by Nginx + Let's Encrypt

---

## Delivery

The post-Foundation contract promotes one immutable frontend/backend commit:

1. Manually deploy the shared feature branch to isolated development.
2. After explicit merge approval, deploy the approved `main` commit to isolated
   test.
3. After separate production approval, deploy only the matching immutable
   `prod-vX.Y.Z` tag.

The standard GitHub configuration names are `DEV_HOST`, `TEST_HOST`,
`PROD_HOST`, and `DEPLOY_SSH_KEY`. Values remain in GitHub/server-side
configuration and are verified only by name and presence.

The repository is still transitioning from its legacy direct-production
workflow. Do not merge, tag, deploy, or alter infrastructure based only on this
README; follow [docs/delivery.md](docs/delivery.md).

---

## Local development

### Python backend

```bash
python -m venv venv
venv/Scripts/activate        # Windows
pip install -r requirements.txt

# Needs an explicitly isolated local Postgres instance
Copy-Item .env.example .env  # fill in local-only DATABASE_URL and SECRET_KEY
$env:PYTHONPATH='src'
uvicorn satt.main:app --reload --port 8200
```

### Frontend

Open `http://localhost:8200`. In the local environment FastAPI serves only the
explicit public HTML, CSS, JavaScript, and image assets; it does not expose
`.env`, backend source, or repository metadata. Browser API calls use
same-origin `/api` and `/public` paths in every environment.

### Tests

```bash
TEST_DATABASE_URL=<isolated-test-database-url> PYTHONPATH=src \
  pytest src/satt/tests/ -v
```

Database-backed tests require an explicit isolated `TEST_DATABASE_URL`, skip
when it is absent, and refuse to run when it matches `DATABASE_URL`. Never run
them against production.

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

Each deployment supplies its own server-side `.env`. Canonical settings are:

| Tier | `ENVIRONMENT` / `DATABASE_ENVIRONMENT` | `SITE_URL` and allowed CORS origin |
|---|---|---|
| Local | `local` | `http://localhost:8200` |
| Development | `development` | `https://dev.saltallthethings.com` |
| Test | `test` | `https://test.saltallthethings.com` |
| Production | `production` | `https://saltallthethings.com` |

`DATABASE_ENVIRONMENT` must match `ENVIRONMENT`. Non-production refuses the
production origin and refuses configured Google OAuth credentials unless
`ALLOW_NONPRODUCTION_EXTERNAL_SERVICES=true` is deliberately set for an
authorized smoke test. Each non-production environment still requires its own
database, credentials, and Drive resources.

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
