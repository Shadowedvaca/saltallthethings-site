# Dockerify SATT — Implementation Plan

**Feature branch:** `feature/dockerify-site`

---

## Background

SATT currently runs as a bare Python process managed by `systemd` (`satt.service` on port 8200).
Static files are served by Nginx from `/opt/satt-platform/static/`.
There is a single `deploy.yml` workflow that deploys to production on every push to `main` — no
dev or test gate.

This plan converts SATT to the same Docker pattern that PATT now uses, and aligns CI/CD with the
canonical workflow in `reference/git-cicd-workflow.md`.

---

## Reference: PATT Docker Setup (model to follow)

| File | Purpose |
|------|---------|
| `Dockerfile` | Single image for all environments |
| `docker-compose.guild.yml` | Three DBs + three app services (prod/test/dev) |
| `Caddyfile.guild` | Caddy virtual hosts for all three environments, basic auth on test/dev |
| `deploy/setup_postgres.sql` | Schema init mounted into Postgres init dir |
| `.env.prod` / `.env.test` / `.env.dev` | Per-environment env files (not committed) |
| `.github/workflows/deploy-dev.yml` | `workflow_dispatch` with `branch` input |
| `.github/workflows/deploy-test.yml` | `push: branches: [main]` |
| `.github/workflows/deploy-prod.yml` | `push: tags: ['prod-*']` |
| `docker-entrypoint.sh` | Runs `alembic upgrade head` then `uvicorn` |

---

## Key Differences from PATT

| Concern | PATT | SATT |
|---------|------|------|
| Static files | Jinja2 templates (served by app) | Raw HTML/CSS/JS (served by shared Caddy `file_server`) |
| App port (internal) | 8100 | 8200 |
| App module | `guild_portal.app:create_app --factory` | `satt.main:app` |
| Database schemas | `common`, `guild_identity`, `patt` | `satt`, `common` |
| Extra env vars | Blizzard API, Discord bot | Google OAuth (Drive), sv_export_key |

---

## Reverse Proxy Architecture: Shared Server-Level Caddy

SATT uses the **same shared Caddy instance** that already serves PATT. Caddy runs at the host
level (not inside SATT's compose stack), so it can proxy to both PATT and SATT app containers
via `localhost` ports.

Consequences:
- SATT app containers **expose ports to the host** (8200, 8201, 8202)
- **No Caddy service in `docker-compose.satt.yml`**
- SATT's virtual host config is added to the server's shared Caddyfile alongside PATT's entries
- Caddy continues to handle SSL (automatic ACME) and basic auth for test/dev
- Static files are served by Caddy via `file_server` pointing at host directories

---

## Port Plan

| Service | Internal port | Host port | Purpose |
|---------|---------------|-----------|---------|
| app-prod | 8200 | 8200 | Caddy proxies here for `saltallthethings.com` |
| app-test | 8200 | 8201 | Caddy proxies here for `test.saltallthethings.com` |
| app-dev | 8200 | 8202 | Caddy proxies here for `dev.saltallthethings.com` |
| db-test | 5432 | 5433 | pytest on host |

---

## Environment URLs

| Environment | URL | Auth |
|-------------|-----|------|
| prod | `saltallthethings.com` | public |
| test | `test.saltallthethings.com` | Caddy basic auth |
| dev | `dev.saltallthethings.com` | Caddy basic auth |

`salt.shadowedvaca.com` (current staging URL) can be retired once test is verified.

DNS A records for `test.saltallthethings.com` and `dev.saltallthethings.com` must point to
`5.78.114.224` before Caddy will issue certs for them.

---

## Phase 1: Docker Infrastructure Files

### 1.1 `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# asyncpg needs libpq; bcrypt needs gcc
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

ENV PYTHONPATH=/app/src

EXPOSE 8200

ENTRYPOINT ["./docker-entrypoint.sh"]
```

Note: SATT's migrations live under `src/satt/migrations/` and are included via `COPY src/ src/`.
The `alembic.ini` at the repo root must be copied separately so `alembic upgrade head` can find it.

### 1.2 `docker-entrypoint.sh`

```bash
#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting Salt All The Things..."
exec uvicorn satt.main:app \
    --host 0.0.0.0 \
    --port 8200 \
    --workers 1
```

### 1.3 `docker-compose.satt.yml`

No Caddy service — the shared host-level Caddy handles routing. App containers expose host ports
directly.

```yaml
services:
  # --- DATABASES ---
  db-prod:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: satt_user
      POSTGRES_PASSWORD: ${PROD_DB_PASSWORD}
      POSTGRES_DB: satt_db
    volumes:
      - satt_pgdata_prod:/var/lib/postgresql/data
      - ./deploy/setup_postgres.sql:/docker-entrypoint-initdb.d/01-setup.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U satt_user"]
      interval: 5s
      timeout: 3s
      retries: 5

  db-test:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: satt_user
      POSTGRES_PASSWORD: ${TEST_DB_PASSWORD}
      POSTGRES_DB: satt_db_test
    volumes:
      - satt_pgdata_test:/var/lib/postgresql/data
      - ./deploy/setup_postgres.sql:/docker-entrypoint-initdb.d/01-setup.sql
    ports:
      - "5433:5432"   # exposed so pytest can reach it from the host
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U satt_user"]
      interval: 5s
      timeout: 3s
      retries: 5

  db-dev:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: satt_user
      POSTGRES_PASSWORD: ${DEV_DB_PASSWORD}
      POSTGRES_DB: satt_db_dev
    volumes:
      - satt_pgdata_dev:/var/lib/postgresql/data
      - ./deploy/setup_postgres.sql:/docker-entrypoint-initdb.d/01-setup.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U satt_user"]
      interval: 5s
      timeout: 3s
      retries: 5

  # --- APPS ---
  app-prod:
    build: .
    restart: unless-stopped
    depends_on:
      db-prod:
        condition: service_healthy
    env_file:
      - .env.prod
    ports:
      - "8200:8200"

  app-test:
    build: .
    restart: unless-stopped
    depends_on:
      db-test:
        condition: service_healthy
    env_file:
      - .env.test
    ports:
      - "8201:8200"

  app-dev:
    build: .
    restart: unless-stopped
    depends_on:
      db-dev:
        condition: service_healthy
    env_file:
      - .env.dev
    ports:
      - "8202:8200"

volumes:
  satt_pgdata_prod:
  satt_pgdata_test:
  satt_pgdata_dev:
```

### 1.4 `deploy/setup_postgres.sql`

```sql
-- SATT PostgreSQL schema setup
-- Mounted as /docker-entrypoint-initdb.d/01-setup.sql in Docker Postgres containers.
-- Run manually as a postgres superuser for bare-metal installs.
--
-- Docker creates the user/database via POSTGRES_USER / POSTGRES_DB env vars.
-- This script only creates schemas and grants permissions.

CREATE SCHEMA IF NOT EXISTS satt;
CREATE SCHEMA IF NOT EXISTS common;

DO $$
BEGIN
    EXECUTE format('GRANT ALL ON SCHEMA satt TO %I', current_user);
    EXECUTE format('GRANT ALL ON SCHEMA common TO %I', current_user);
END
$$;
```

---

## Phase 2: Shared Caddy Configuration

Add SATT's virtual hosts to the server's shared Caddyfile (the same one that serves PATT).
Caddy proxies to `localhost:820X` for API calls and serves static files from host directories
via `file_server`.

### SATT block to add to the shared Caddyfile

```
saltallthethings.com {
    root * /opt/satt-platform/static
    file_server

    reverse_proxy /api/* localhost:8200
    reverse_proxy /public/* localhost:8200
}

test.saltallthethings.com {
    basicauth {
        admin {$SATT_TEST_AUTH_HASH}
    }

    root * /opt/satt-platform/static-test
    file_server

    reverse_proxy /api/* localhost:8201
    reverse_proxy /public/* localhost:8202
}

dev.saltallthethings.com {
    basicauth {
        admin {$SATT_DEV_AUTH_HASH}
    }

    root * /opt/satt-platform/static-dev
    file_server

    reverse_proxy /api/* localhost:8202
    reverse_proxy /public/* localhost:8202
}
```

`SATT_TEST_AUTH_HASH` and `SATT_DEV_AUTH_HASH` are bcrypt hashes added to the environment that
Caddy reads. Generate them with:

```bash
caddy hash-password --plaintext 'choose-a-test-password'
```

After adding the blocks and updating env vars, reload Caddy:

```bash
caddy reload --config /path/to/Caddyfile
# or if Caddy runs as a systemd service:
sudo systemctl reload caddy
```

---

## Phase 3: Environment Config Templates

Real files (`.env.prod`, `.env.test`, `.env.dev`) are never committed — they live only on the
server. A root `.env` (not committed) holds the DB password vars for docker-compose variable
substitution.

### Root `.env` (docker-compose variable substitution only)

```bash
PROD_DB_PASSWORD=
TEST_DB_PASSWORD=
DEV_DB_PASSWORD=
```

### `.env.prod.example`

```bash
# Database — service name resolves within Docker network
DATABASE_URL=postgresql+asyncpg://satt_user:CHANGEME@db-prod:5432/satt_db

# Auth
SECRET_KEY=       # openssl rand -hex 32

# App
ENVIRONMENT=production
SITE_URL=https://saltallthethings.com
CORS_ORIGINS=https://saltallthethings.com
AI_REQUEST_TIMEOUT=60

# Google Drive OAuth
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REFRESH_TOKEN=

# sv-tools server-to-server
SV_EXPORT_KEY=
```

### `.env.test.example` / `.env.dev.example`

Same structure. Change:
- `DATABASE_URL` service name: `db-test` / `db-dev`
- `ENVIRONMENT`: `test` / `development`
- `SITE_URL` / `CORS_ORIGINS`: appropriate subdomain
- Separate `SECRET_KEY`

---

## Phase 4: GitHub Actions Workflows

Replace the existing `deploy.yml` with three new workflows. Each workflow:
1. SSHes to the server
2. Checks out the appropriate branch or tag
3. Copies static files to the correct host directory (served by Caddy)
4. Builds and restarts the appropriate app container
5. Health-checks via direct `localhost` port (bypasses Caddy basic auth, no extra secrets needed)

All three use `appleboy/ssh-action@v1.2.0` and the `DEPLOY_SSH_KEY` secret.

### `.github/workflows/deploy-dev.yml`

```yaml
name: Deploy to Dev

on:
  workflow_dispatch:
    inputs:
      branch:
        description: 'Branch to deploy to dev'
        required: true
        default: 'main'

jobs:
  deploy:
    name: Deploy to dev.saltallthethings.com
    runs-on: ubuntu-latest
    steps:
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1.2.0
        with:
          host: 5.78.114.224
          username: root
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            set -e
            cd /opt/satt-platform

            echo "==> Fetching branch: ${{ github.event.inputs.branch }}..."
            git fetch origin
            git checkout ${{ github.event.inputs.branch }}
            git pull origin ${{ github.event.inputs.branch }}

            echo "==> Copying static files to dev..."
            mkdir -p static-dev
            cp *.html static-dev/
            cp -r css js images static-dev/

            echo "==> Building dev image..."
            docker compose -f docker-compose.satt.yml build app-dev

            echo "==> Restarting dev app..."
            docker compose -f docker-compose.satt.yml up -d app-dev

            echo "==> Waiting for dev to be ready..."
            for i in $(seq 1 10); do
              sleep 3
              if curl -sf http://localhost:8202/api/health \
                  | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('ok') else 1)" 2>/dev/null; then
                echo "==> Dev healthy after ${i}x3s"
                break
              fi
              if [ $i -eq 10 ]; then
                echo "ERROR: Dev did not become healthy"
                docker compose -f docker-compose.satt.yml logs app-dev --tail 30
                exit 1
              fi
            done

            echo "==> Dev deploy complete! https://dev.saltallthethings.com"
```

### `.github/workflows/deploy-test.yml`

- Trigger: `push: branches: [main]`
- Same pattern: checkout main, copy static to `static-test/`, build/restart `app-test`,
  health check `http://localhost:8201/api/health`

### `.github/workflows/deploy-prod.yml`

- Trigger: `push: tags: ['prod-*']`
- Same pattern: checkout tag, copy static to `static/`, build/restart `app-prod`,
  health check `http://localhost:8200/api/health`

**GitHub Secrets needed:**

| Secret | Notes |
|--------|-------|
| `DEPLOY_SSH_KEY` | Same ed25519 key PATT uses — check if it already exists in this repo |
| `STAGING_SSH_KNOWN_HOSTS` | Already exists in this repo |

> Health checks hit `localhost:820X` directly, so no basic auth credentials are needed in the
> workflow secrets. Caddy basic auth only applies to external HTTPS traffic.

> If only `STAGING_SSH_KEY` exists (not `DEPLOY_SSH_KEY`), check the exact secret name in repo
> settings and use it — or add `DEPLOY_SSH_KEY` pointing to the same key.

---

## Phase 5: Server-Side Setup

Docker is already installed (PATT uses it). Run these steps on the Hetzner server.

### 5.1 Create directory structure

```bash
mkdir -p /opt/satt-platform/deploy
mkdir -p /opt/satt-platform/static-test
mkdir -p /opt/satt-platform/static-dev
# /opt/satt-platform/static already exists
```

### 5.2 Create env files

```bash
cd /opt/satt-platform

# Root .env for docker-compose variable substitution
cat > .env << 'EOF'
PROD_DB_PASSWORD=
TEST_DB_PASSWORD=
DEV_DB_PASSWORD=
EOF

# Per-environment app env files
cp .env.prod.example .env.prod   # fill in all values
cp .env.test.example .env.test
cp .env.dev.example .env.dev
```

### 5.3 DNS — add A records before reloading Caddy

Add DNS A records pointing to `5.78.114.224`:
- `test.saltallthethings.com`
- `dev.saltallthethings.com`

Verify propagation with `dig test.saltallthethings.com` before reloading Caddy.

### 5.4 Add SATT blocks to the shared Caddyfile, reload

Add the three virtual host blocks from Phase 2 to the server's shared Caddyfile.
Add `SATT_TEST_AUTH_HASH` and `SATT_DEV_AUTH_HASH` to the environment Caddy reads from.
Reload Caddy. Verify no config errors before proceeding.

### 5.5 Start databases

```bash
cd /opt/satt-platform
docker compose -f docker-compose.satt.yml up -d db-prod db-test db-dev
docker compose -f docker-compose.satt.yml ps   # wait for all three healthy
```

### 5.6 Migrate existing data from host Postgres

Export the `satt` and `common` schemas from the host Postgres instance into the prod DB:

```bash
# Export
pg_dump -h localhost -U satt_user -n satt -n common \
    --no-owner --no-acl \
    -f /tmp/satt_export.sql satt_db

# Import into Docker prod DB
docker exec -i $(docker compose -f docker-compose.satt.yml ps -q db-prod) \
    psql -U satt_user -d satt_db < /tmp/satt_export.sql
```

Verify row counts match before proceeding:
```bash
# Host Postgres
psql -h localhost -U satt_user satt_db -c "SELECT COUNT(*) FROM satt.users;"

# Docker prod DB
docker exec $(docker compose -f docker-compose.satt.yml ps -q db-prod) \
    psql -U satt_user satt_db -c "SELECT COUNT(*) FROM satt.users;"
```

### 5.7 Copy static files to serve directories

```bash
cd /opt/satt-platform
# static/ already contains current prod files from the old deploy
# seed test and dev with a copy (CI/CD will keep them updated after this)
cp -r static/* static-test/
cp -r static/* static-dev/
```

### 5.8 Start app containers

```bash
docker compose -f docker-compose.satt.yml build
docker compose -f docker-compose.satt.yml up -d app-prod app-test app-dev
```

Health check all three directly:
```bash
curl -sf http://localhost:8200/api/health
curl -sf http://localhost:8201/api/health
curl -sf http://localhost:8202/api/health
```

Then verify through Caddy (confirms SSL + routing work):
```bash
curl -sf https://saltallthethings.com/api/health
```

### 5.9 Stop and disable the systemd unit

Only after confirming prod is healthy through Caddy:

```bash
sudo systemctl stop satt
sudo systemctl disable satt
```

---

## Phase 6: Remove SATT from the Old Reverse Proxy

Remove the `saltallthethings.com` vhost from wherever it previously lived (Nginx or a prior
Caddy config entry). Confirm other sites are unaffected after the change.

> **Do not touch vhosts for `shadowedvaca.com`, `pullallthethings.com`, or any other site.**

---

## Phase 7: Test Runner Update

With the test DB in Docker (port 5433 on host), update the pytest command:

```bash
cd /opt/satt-platform
TEST_DATABASE_URL=postgresql+asyncpg://satt_user:TEST_DB_PASSWORD@localhost:5433/satt_db_test \
  PYTHONPATH=src venv/bin/pytest src/satt/tests/ -v
```

Update `CLAUDE.md` and memory with the new test command once confirmed working.

---

## Phase 8: Cleanup

- Delete `.github/workflows/deploy.yml` (old push-to-main-deploys-prod workflow)
- Update `src/satt/config.py` default `cors_origins`: remove `salt.shadowedvaca.com`,
  add `test.saltallthethings.com`
- Update `CLAUDE.md`:
  - Remove systemd unit references for `satt`
  - Add Docker compose commands for start/stop/logs
  - Update test command with new `TEST_DATABASE_URL`
  - Replace staging URL `salt.shadowedvaca.com` → `test.saltallthethings.com`

---

## Verification Checklist

- [ ] `https://saltallthethings.com` loads static site + login works (prod)
- [ ] `https://test.saltallthethings.com` loads (behind basic auth, test DB)
- [ ] `https://dev.saltallthethings.com` loads (behind basic auth, dev DB)
- [ ] Post-production page and Google Drive scan work on prod
- [ ] `deploy-dev.yml` workflow_dispatch deploys a feature branch to dev
- [ ] Push to `main` auto-deploys to test
- [ ] `prod-*` tag auto-deploys to prod
- [ ] Pytest passes: `TEST_DATABASE_URL=...localhost:5433... pytest`
- [ ] `sudo systemctl status satt` shows `disabled` / `dead`
- [ ] Old SATT reverse proxy vhost removed; other sites return 200

---

## Rollback Plan

**Before systemd unit is disabled (safest window):**
```bash
docker compose -f docker-compose.satt.yml down
# Remove SATT blocks from shared Caddyfile, reload Caddy
# Old systemd unit kept running throughout — no data loss
```

**After systemd unit is disabled:**
```bash
sudo systemctl enable satt
sudo systemctl start satt
# Restore old reverse proxy vhost if removed
```

---

## Useful Docker Commands (post-migration)

```bash
# Logs
docker compose -f /opt/satt-platform/docker-compose.satt.yml logs app-prod -f
docker compose -f /opt/satt-platform/docker-compose.satt.yml logs app-dev -f

# Run a migration manually on dev
docker exec $(docker compose -f /opt/satt-platform/docker-compose.satt.yml ps -q app-dev) \
    alembic upgrade head

# Access dev DB directly
docker exec -it $(docker compose -f /opt/satt-platform/docker-compose.satt.yml ps -q db-dev) \
    psql -U satt_user satt_db_dev

# Restart one service
docker compose -f /opt/satt-platform/docker-compose.satt.yml restart app-prod
```

---

*Plan written: 2026-03-17*
*Reference: `reference/git-cicd-workflow.md`, PATT `docker-compose.guild.yml`, PATT `Caddyfile.guild`*
