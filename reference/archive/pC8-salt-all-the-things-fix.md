# pC8 — Podcast Sync Fix (SATT side)

## Background

sv-tools needs to pull the full podcast dataset (ideas, jokes, show slots,
assignments) from SATT on a regular basis. The old Cloudflare Worker `/export`
endpoint is no longer the source of truth — data now lives in Postgres, served
by the FastAPI backend.

This adds a lightweight server-to-server export endpoint protected by a static
API key, mounted under the existing `/public` prefix so no Nginx changes are
needed.

## Files Changed

| File | Change |
|------|--------|
| `src/satt/config.py` | Add `sv_export_key: str = ""` to Settings |
| `src/satt/routes/public.py` | Add `GET /sv-export?key=<secret>` route |
| `/opt/satt-platform/.env` (server) | Add `SV_EXPORT_KEY=<secret>` |

## Implementation

### 1. `src/satt/config.py`

Add one field to the `Settings` class, below the JWT block:

```python
# sv-tools server-to-server export key
sv_export_key: str = ""
```

### 2. `src/satt/routes/public.py`

Add the following imports at the top (merge with existing imports):

```python
from fastapi import HTTPException
from satt.config import get_settings
from satt.crud import get_assignments, get_config, get_ideas, get_jokes, get_show_slots
```

Add the route at the bottom of the file:

```python
@router.get("/sv-export")
async def sv_export(
    key: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Server-to-server export for sv-tools. Protected by static API key."""
    settings = get_settings()
    if not settings.sv_export_key or key != settings.sv_export_key:
        raise HTTPException(status_code=403, detail="Forbidden")
    config, ideas, jokes, show_slots, assignments = (
        await get_config(db),
        await get_ideas(db),
        await get_jokes(db),
        await get_show_slots(db),
        await get_assignments(db),
    )
    return JSONResponse(content={
        "config": config,
        "ideas": ideas,
        "jokes": jokes,
        "showSlots": show_slots,
        "assignments": assignments,
    })
```

No changes to `main.py` — the public router is already mounted at `/public`.

Final URL: `https://saltallthethings.com/public/sv-export?key=<secret>`

### 3. Server `.env`

Generate a key and add it to `/opt/satt-platform/.env`:

```bash
# Generate:
openssl rand -hex 32

# Add to /opt/satt-platform/.env:
SV_EXPORT_KEY=<generated value>
```

Use the same value for `satt_api_password` in sv-tools `machine.yaml`.

## Deploy

```bash
cd /opt/satt-platform
git pull
# Edit /opt/satt-platform/.env and add SV_EXPORT_KEY=<secret>
sudo systemctl restart satt
sudo systemctl status satt
```

## Verify

```bash
# Should return 200 with full JSON:
curl -s "https://saltallthethings.com/public/sv-export?key=<secret>" \
  | python3 -m json.tool | head -30

# Should return 403:
curl -s -o /dev/null -w "%{http_code}" \
  "https://saltallthethings.com/public/sv-export?key=wrong"

# Should return 422 (missing required param):
curl -s -o /dev/null -w "%{http_code}" \
  "https://saltallthethings.com/public/sv-export"
```

## After SATT Is Deployed

Hand off to sv-tools side: `pC8-podcast-sync-fix.md`
Provide the `SV_EXPORT_KEY` value so it can be set in both local and server
`machine.yaml`.
