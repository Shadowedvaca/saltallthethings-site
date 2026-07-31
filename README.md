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

The legacy push-to-`main` production job has been removed. Production is now
represented only by the validated tag-gated workflow, but it is not configured
or authorized merely because the workflow exists. Do not merge, tag, deploy, or
alter infrastructure based only on this README; follow
[docs/delivery.md](docs/delivery.md) and the separately authorized
[production cutover runbook](docs/production-cutover.md).

Semantic version changes, curated notes, tag validation, GitHub Release
publication, hotfixes, and rollback versions are described in
[docs/versioning-and-releases.md](docs/versioning-and-releases.md).

### Container runtime

`Dockerfile` is the production runtime definition. It installs locked runtime
dependencies, runs as an unprivileged user, validates environment/data
ownership, applies Alembic migrations, and then starts FastAPI. The same image
contains the explicitly public frontend and backend.

For a disposable local environment:

```powershell
docker compose -f compose.yaml -f compose.local.yaml up --build --wait
```

Development and test use `compose.development.yaml` and `compose.test.yaml`
with separately supplied database components, secrets, host port, and commit.
Their named database volumes are distinct. `compose.production.yaml` contains
only the application service and never provisions a development or test
database on the production host.

Do not print expanded Compose configuration: interpolation can contain
secret-bearing values. Validate configuration by exit status, configured
presence, or one-way fingerprint only.

---

## Local development

### Python backend

```bash
python -m venv venv
venv/Scripts/activate        # Windows
pip install -r requirements-dev.txt

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

The Docker-based local runtime is preferred when Docker is available because
it also validates the entrypoint, fresh-database migration, and health contract.

### Tests

```bash
TEST_DATABASE_URL=<isolated-test-database-url> PYTHONPATH=src \
  pytest src/satt/tests/ -v
```

Database-backed tests require an explicit isolated `TEST_DATABASE_URL`, skip
when it is absent, and refuse to run when it matches `DATABASE_URL`. Never run
them against production.

Pull requests run the complete database suite against an ephemeral
loopback-only PostgreSQL service and separately build and inspect the production
image against a fresh isolated container database. The workflow has read-only
repository permission and no deployment trigger or production configuration.

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
