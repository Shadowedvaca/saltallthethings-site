# Phase 4 — Nginx + SSL + DNS Cutover

## Goal
Move `saltallthethings.com` off GitHub Pages and onto Hetzner. Configure Nginx,
provision SSL, flip DNS, smoke test production, and decommission all Cloudflare
Worker and GitHub Pages dependencies. After this phase, the migration is complete.

## Deliverables
- [ ] Nginx server block configured for `saltallthethings.com` and `salt.shadowedvaca.com`
- [ ] SSL cert provisioned via Certbot for both domains
- [ ] Systemd unit `satt` running and enabled
- [ ] DNS A record for `saltallthethings.com` pointing to `5.78.114.224`
- [ ] Production data migration complete (Cloudflare KV → Postgres)
- [ ] All 4 pages smoke tested on production domain
- [ ] Cloudflare Worker decommissioned
- [ ] GitHub Pages disabled
- [ ] X-Auth bridge removed from FastAPI
- [ ] GitHub Actions deploy workflow updated for new deploy target

---

## Server Context

- **Server:** Hetzner, IP `5.78.114.224`
- **Deploy path:** `/opt/satt-platform/`
- **PYTHONPATH:** `/opt/satt-platform/src`
- **Systemd unit name:** `satt`
- **Port:** `8200` (internal only — never exposed directly)
- **Static files:** `/opt/satt-platform/static/`
- **Existing sites on this server:**
  - `shadowedvaca.com` — Meandering Muck project
  - `pullallthethings.com` — PATT project (port `8100`, unit `patt`)
  - `saltallthethings.com` — this project (port `8200`, unit `satt`)
- **DNS provider:** Cloudflare (for `saltallthethings.com`)

---

## Step 1 — Systemd Unit

Create `/etc/systemd/system/satt.service`:

```ini
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
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable satt
sudo systemctl start satt
sudo systemctl status satt
# confirm: Active: active (running)

# Verify it's up before touching Nginx
curl http://127.0.0.1:8200/health
# → {"status": "ok", "timestamp": "..."}
```

---

## Step 2 — Nginx Configuration

**Check existing Nginx config first.** Look at the PATT and shadowedvaca server
blocks for the established patterns on this server before writing the SATT block.
Match the same structure — do not invent a new pattern.

Create `/etc/nginx/sites-available/saltallthethings`:

```nginx
# Salt All The Things
# Staging subdomain
server {
    listen 80;
    server_name salt.shadowedvaca.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name salt.shadowedvaca.com;

    ssl_certificate     /etc/letsencrypt/live/salt.shadowedvaca.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/salt.shadowedvaca.com/privkey.pem;
    include             /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam         /etc/letsencrypt/ssl-dhparams.pem;

    root /opt/satt-platform/static;
    index index.html;

    # Static files
    location / {
        try_files $uri $uri/ /index.html;
    }

    # FastAPI backend
    location /api/ {
        proxy_pass         http://127.0.0.1:8200/;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 90s;
    }

    # Public endpoints (no /api/ prefix on these)
    location /public/ {
        proxy_pass         http://127.0.0.1:8200/public/;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}

# Production domain
server {
    listen 80;
    server_name saltallthethings.com www.saltallthethings.com;
    return 301 https://saltallthethings.com$request_uri;
}

server {
    listen 443 ssl;
    server_name saltallthethings.com www.saltallthethings.com;

    ssl_certificate     /etc/letsencrypt/live/saltallthethings.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/saltallthethings.com/privkey.pem;
    include             /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam         /etc/letsencrypt/ssl-dhparams.pem;

    root /opt/satt-platform/static;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass         http://127.0.0.1:8200/;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 90s;
    }

    location /public/ {
        proxy_pass         http://127.0.0.1:8200/public/;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/saltallthethings \
           /etc/nginx/sites-enabled/saltallthethings
sudo nginx -t
# confirm: syntax is ok / test is successful
```

**Do not reload Nginx yet** — get the certs first.

---

## Step 3 — SSL Certificates

Get certs for staging domain first, verify it works, then production.

```bash
# Staging cert (salt.shadowedvaca.com should already be resolving to this server)
sudo certbot --nginx -d salt.shadowedvaca.com

# Verify staging HTTPS works before touching production DNS
curl https://salt.shadowedvaca.com/health
# → {"status": "ok", ...}

# Production cert — run AFTER DNS cutover in Step 4
sudo certbot --nginx -d saltallthethings.com -d www.saltallthethings.com
```

```bash
sudo systemctl reload nginx
```

---

## Step 4 — Production Data Migration

Run the migration script from Phase 1 against the live Cloudflare Worker.
Do this before DNS cutover so both systems have the same data at the moment
of cutover.

```bash
cd /opt/satt-platform
PYTHONPATH=src python src/satt/scripts/migrate_from_cloudflare.py \
  --api-url https://satt-worker.shadowedvaca.workers.dev \
  --password <admin_password>
```

Expected output:
```
Migrating from Cloudflare KV...
  config:      1 row upserted
  ideas:       N rows upserted
  jokes:       N rows upserted
  show_slots:  N rows upserted
  assignments: N rows upserted
Migration complete. Cloudflare Worker is still live — do not decommission yet.
```

Verify data in Postgres before proceeding:
```bash
psql -c "SELECT COUNT(*) FROM satt.ideas;"
psql -c "SELECT COUNT(*) FROM satt.jokes;"
psql -c "SELECT episode_number, record_date, release_date FROM satt.show_slots ORDER BY episode_num LIMIT 5;"
```

---

## Step 5 — DNS Cutover

**This is the point of no return. Staging must be fully verified before this step.**

In Cloudflare DNS for `saltallthethings.com`:

1. Note the current A record value (GitHub Pages IP) — write it down
2. Change A record for `saltallthethings.com` → `5.78.114.224`
3. Change A record for `www.saltallthethings.com` → `5.78.114.224`
4. Set TTL to 1 minute (so rollback is fast if needed)
5. **Disable Cloudflare proxy (orange cloud → grey cloud)** for both records
   during cutover — you want direct DNS, not Cloudflare proxying to the old
   GitHub Pages IP

```bash
# After DNS propagates (watch with watch -n5 dig saltallthethings.com)
# Get production SSL cert
sudo certbot --nginx -d saltallthethings.com -d www.saltallthethings.com
sudo systemctl reload nginx
```

---

## Step 6 — Production Smoke Test

Run this full checklist against `https://saltallthethings.com` before
decommissioning anything:

**Public pages**
- [ ] `https://saltallthethings.com` loads, hero renders correctly
- [ ] YouTube embeds work (if video IDs configured)
- [ ] All platform links (Spotify, Apple, YouTube, Amazon, RSS) resolve
- [ ] Discord link works
- [ ] Patreon / Buy Me a Coffee / Ko-fi / PayPal links work
- [ ] `https://saltallthethings.com/public/episodes` returns JSON
- [ ] `https://saltallthethings.com/public/homepage` returns video IDs

**Auth flow**
- [ ] `show_management.html` shows password gate
- [ ] Wrong password: shake animation, error message
- [ ] Correct password: gate dismisses, data loads from Postgres
- [ ] Session persists on refresh
- [ ] Logout clears session, gate reappears

**Show Management**
- [ ] Existing ideas loaded from Postgres (verify count matches migration)
- [ ] Drag-and-drop schedule board loads slots correctly
- [ ] Create a new idea → saves to Postgres → verify with:
  ```bash
  psql -c "SELECT COUNT(*) FROM satt.ideas;"
  ```
- [ ] Assign an idea to a slot → verify assignment saved

**Jokes**
- [ ] Existing jokes loaded (verify count matches migration)
- [ ] Add a manual joke → appears in list → saved to Postgres
- [ ] Generate AI jokes → proxy call succeeds → suggestions appear
  (requires API key configured in config)

**Config**
- [ ] Config page loads with existing settings
- [ ] Generate invite code button works → URL appears → copy button works
- [ ] Register page (`/register.html`) loads with a valid invite code

**RSS / External**
- [ ] RSS feed still resolves (this is served by Spotify for Podcasters, not your
  server — just verify the link on the page still works)

---

## Step 7 — Decommission X-Auth Bridge

Now that production is verified on JWT auth, remove the temporary bridge.

**In `src/satt/auth_bridge.py`:** Delete the file.

**In `src/satt/routes/data.py` and any other route that uses the bridge:**
Remove all `X-Auth` header handling. All routes now require JWT only.

**In `src/satt/routes/ai.py`:** Verify no X-Auth references.

```bash
# Confirm no X-Auth references remain
grep -r "X-Auth\|x_auth\|xauth" src/satt/
# → no results

# Restart service
sudo systemctl restart satt
curl -H "X-Auth: anything" https://saltallthethings.com/api/export
# → 401 (bridge is gone)

# JWT still works
curl -H "Authorization: Bearer <token>" https://saltallthethings.com/api/export
# → 200
```

---

## Step 8 — Decommission GitHub Pages

**In `.github/workflows/deploy.yml`:**

Remove the entire GitHub Pages deployment step. The workflow can be deleted
entirely or kept as a no-op if you want to preserve history.

**In GitHub repo settings:**
1. Go to Settings → Pages
2. Set Source to "None" — GitHub Pages disabled

**Verify:**
```bash
curl https://shadowedvaca.github.io/saltallthethings-site/
# → 404 (Pages disabled)

curl https://saltallthethings.com/
# → 200 (Hetzner serving it)
```

---

## Step 9 — Decommission Cloudflare Worker

Only do this after:
- Production smoke test passes ✓
- X-Auth bridge removed ✓
- Postgres confirmed as source of truth ✓

In the Cloudflare dashboard:
1. Go to Workers & Pages → `satt-worker` (or whatever it's named)
2. Disable the worker route for `saltallthethings.com/*`
3. Optionally delete the worker entirely — but consider keeping it for 7 days
   as a safety net in case something surfaces post-cutover

```bash
# Final verification — worker is gone, site still works
curl https://saltallthethings.com/public/episodes
# → data from Postgres, not Cloudflare KV
```

---

## Rollback Plan

If something goes wrong after DNS cutover:

1. **Revert DNS** — change A record back to GitHub Pages IP in Cloudflare
   (TTL is 1 minute, propagates fast)
2. **GitHub Pages** is still active until Step 8 — it comes back immediately
3. **Cloudflare Worker** is still live until Step 9 — data still there
4. Investigate, fix, re-attempt cutover

The staging environment (`salt.shadowedvaca.com`) remains available after
cutover for future testing.

---

## What NOT To Do In This Phase

- Do not delete Cloudflare Worker data before Postgres is verified as source of truth
- Do not disable GitHub Pages before production smoke test passes
- Do not remove X-Auth bridge before JWT auth is confirmed working in production
- Do not set DNS TTL back to a long value until you're confident in the new stack

---

## Definition of Done

```bash
# Service running
sudo systemctl status satt
# → active (running)

# Production site live
curl -I https://saltallthethings.com
# → HTTP/2 200

# No GitHub Pages
curl https://shadowedvaca.github.io/saltallthethings-site/
# → 404

# No X-Auth
curl -H "X-Auth: anything" https://saltallthethings.com/api/export
# → 401

# Postgres is source of truth
psql -c "SELECT COUNT(*) FROM satt.ideas;"
# → matches your known idea count

# Cloudflare Worker decommissioned
# (verified in Cloudflare dashboard)
```

---

## Post-Migration Cleanup (optional, after 7-day soak)

Once the site has been running stably on Hetzner for a week:

- Delete Cloudflare Worker entirely
- Remove `references/` migration phase docs