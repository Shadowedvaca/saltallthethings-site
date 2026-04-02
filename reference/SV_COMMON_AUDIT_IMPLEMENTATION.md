# sv-common Extraction — Implementation Checklist

> **Status:** Ready to execute
> **Date:** 2026-03-18
> **Based on:** `PullAllTheThings-site/reference/SV_COMMON_AUDIT.md`
> **Scope:** End-to-end implementation plan for extracting sv-common into a standalone package and migrating all three consuming apps

---

## Pre-Work Decisions (Resolve Before Starting)

These were left as open questions in the audit. Answers are needed before Phase SV-1.

| # | Question | Recommended Default |
|---|----------|---------------------|
| 1 | **Repo visibility** — public or private? | Private, under the Shadowedvaca org. No secrets, but no reason to be public either. Install via GitHub deploy key in each app's CI. |
| 2 | **shadowedvaca JWT** — unify with sv-common's parameterized JWT or leave standalone? | Unify. Pass `extra_claims={"username": ..., "is_admin": ...}`. Low effort, eliminates a separate JWT impl. |
| 3 | **Generic config_cache in sv-common?** | Yes — offer a generic `config_cache` (seed from single-row DB, get/set helpers). Each app defines typed accessors on top. Pattern is reusable. |
| 4 | **Does satt need a Discord bot?** | No. satt has no Discord integration. It installs `sv-common` core only (no `[discord]` extra). |

---

## Phase SV-1: Create the sv-common Repo

> **Repo:** `github.com/Shadowedvaca/sv-common`
> **Source of truth:** PATT's current sv_common (most up to date); satt's copy is the older snapshot and is treated as read-only reference.

### 1.1 — Repo Setup

- [ ] Create `github.com/Shadowedvaca/sv-common` (private)
- [ ] Add collaborators: Rocket, Trog (match PATT/satt access)
- [ ] Clone locally
- [ ] Init with `pyproject.toml` (see §1.3 below), `README.md`, `.gitignore`
- [ ] Create directory structure: `sv_common/auth/`, `sv_common/db/`, `sv_common/discord/`, `sv_common/crypto.py`, `sv_common/config_cache.py`, `sv_common/errors/`, `sv_common/feedback/`, `sv_common/notify/`

### 1.2 — Seed Modules (copy from PATT's sv_common)

Copy these files from `PullAllTheThings-site/src/sv_common/` into the new repo. These are the **generic, domain-agnostic** modules only.

| Source (PATT sv_common) | Destination (sv-common repo) | Notes |
|-------------------------|------------------------------|-------|
| `auth/passwords.py` | `sv_common/auth/passwords.py` | Copy as-is |
| `auth/jwt.py` | `sv_common/auth/jwt.py` | **Must fix** — see §1.4 |
| `auth/invite_codes.py` | `sv_common/auth/invite_codes.py` | **Must fix** — see §1.4 |
| `db/engine.py` | `sv_common/db/engine.py` | Copy as-is |
| `crypto.py` | `sv_common/crypto.py` | Copy as-is |
| `config_cache.py` | `sv_common/config_cache.py` | **Must fix** — see §1.4 |
| `errors/` (full dir) | `sv_common/errors/` | Copy as-is |
| `feedback/` (full dir) | `sv_common/feedback/` | Copy as-is |
| `notify/` (full dir) | `sv_common/notify/` | Copy as-is |
| `discord/channels.py` | `sv_common/discord/channels.py` | Generic channel messaging only |
| `discord/dm.py` | `sv_common/discord/dm.py` | Generic DM utilities only |

**Do NOT copy into sv-common:**
- `db/models.py` — stays in each app
- `db/seed.py` — PATT-specific (seeds guild ranks)
- `discord/bot.py` — guild-specific event handlers, moves to `guild_portal`
- `discord/channel_sync.py` — guild_identity schema, moves to `guild_portal`
- `discord/role_sync.py` — GuildRank concept, moves to `guild_portal`
- `discord/voice_attendance.py` — raid attendance, moves to `guild_portal`
- `identity/` (full dir) — WoW guild identity, moves to `guild_portal`
- `guild_sync/` (full dir) — WoW/Blizzard sync, moves to `guild_portal`

### 1.3 — pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "sv-common"
version = "1.0.0"
description = "Shared infrastructure for Shadowedvaca projects"
requires-python = ">=3.11"
dependencies = [
    "PyJWT>=2.8",
    "bcrypt>=4.0",
    "sqlalchemy>=2.0",
    "asyncpg>=0.29",
    "cryptography>=41.0",
]

[project.optional-dependencies]
discord = [
    "discord.py>=2.3",
]
feedback = [
    "httpx>=0.27",
]

[tool.hatch.build.targets.wheel]
packages = ["sv_common"]
```

### 1.4 — Fixes Required Before Tagging v1.0.0

#### Fix 1: Remove app imports from `auth/jwt.py`

The current jwt.py imports from the host app's config. This is what makes sv-common non-portable.

**Current (broken in satt, wrong in PATT):**
```python
from patt.config import get_settings   # satt's copy — patt package no longer exists
from guild_portal.config import get_settings  # PATT's current copy
```

**New sv-common jwt.py — accept all params explicitly:**
```python
def create_access_token(
    secret_key: str,
    user_id: int,
    expires_minutes: int,
    extra_claims: dict | None = None,
    algorithm: str = "HS256",
) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        "iat": datetime.now(timezone.utc),
        **(extra_claims or {}),
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def decode_access_token(
    token: str,
    secret_key: str,
    algorithm: str = "HS256",
) -> dict:
    return jwt.decode(token, secret_key, algorithms=[algorithm])
```

Each app passes `settings.secret_key` and `settings.jwt_expire_minutes` at call site. No sv-common module ever imports an app's config.

#### Fix 2: Parameterize `auth/invite_codes.py`

**Changes:**
- Rename `player_id` / `created_by_user_id` → `owner_id` (generic)
- Remove default expiry value — callers pass explicitly
- Add optional `metadata: dict | None = None` for app-specific fields

```python
def generate_invite_code(
    db,
    owner_id: int,
    expires_hours: int,       # no default — caller must be explicit
    metadata: dict | None = None,
) -> str: ...
```

#### Fix 3: Strip guild-specific getters from `config_cache.py`

`config_cache.py` currently has `get_guild_name()`, `get_home_realm_slug()`, `get_realm_display_name()`, `get_guild_color()` — all guild concepts.

**sv-common keeps:** generic `seed_cache(data: dict)`, `get(key: str)`, `set(key: str, value)` helpers.

**Moves to `guild_portal/config_cache.py`:** all guild-specific getter functions.

#### Fix 4: Strip guild-specific Discord from `discord/channels.py` / `dm.py`

Review both files. Remove any imports of guild-identity models or guild_sync references. These two files should only need `discord.py` as a dependency.

### 1.5 — Port Tests

PATT has tests for sv-common modules. Port relevant ones:

- [ ] `test_passwords.py` — hash/verify round-trip
- [ ] `test_jwt.py` — create/decode, expiry, invalid token; update for new signature
- [ ] `test_invite_codes.py` — generate, validate, consume, expire; update for new signature
- [ ] `test_crypto.py` — encrypt/decrypt round-trip
- [ ] `test_errors.py` — error catalogue lookup
- [ ] `test_config_cache.py` — seed/get/set

### 1.6 — Tag and Publish

- [ ] Run tests: all pass
- [ ] `git tag v1.0.0`
- [ ] `git push origin v1.0.0`
- [ ] Verify install works: `pip install "sv-common @ git+https://github.com/Shadowedvaca/sv-common@v1.0.0"`

---

## Phase SV-2: Relocate Guild Code Inside PATT

> **Repo:** `PullAllTheThings-site`
> **Goal:** Move all WoW/guild-specific code out of `src/sv_common/` into `src/guild_portal/` before deleting sv_common

### 2.1 — Create New Package Structure

Create these directories (with `__init__.py`) in `src/guild_portal/`:

```
src/guild_portal/
├── guild/              ← replaces sv_common/guild_sync/
├── identity/           ← replaces sv_common/identity/
├── discord/            ← replaces guild-specific sv_common/discord/ modules
└── db/                 ← replaces sv_common/db/models.py + db/seed.py
```

### 2.2 — Move Files

| From (`src/sv_common/`) | To (`src/guild_portal/`) |
|-------------------------|--------------------------|
| `guild_sync/blizzard_client.py` | `guild/blizzard_client.py` |
| `guild_sync/scheduler.py` | `guild/scheduler.py` |
| `guild_sync/db_sync.py` | `guild/db_sync.py` |
| `guild_sync/discord_sync.py` | `guild/discord_sync.py` |
| `guild_sync/identity_engine.py` | `guild/identity_engine.py` |
| `guild_sync/crafting_service.py` | `guild/crafting_service.py` |
| `guild_sync/crafting_sync.py` | `guild/crafting_sync.py` |
| `guild_sync/progression_sync.py` | `guild/progression_sync.py` |
| `guild_sync/raiderio_client.py` | `guild/raiderio_client.py` |
| `guild_sync/warcraftlogs_client.py` | `guild/warcraftlogs_client.py` |
| `guild_sync/wcl_sync.py` | `guild/wcl_sync.py` |
| `guild_sync/bnet_character_sync.py` | `guild/bnet_character_sync.py` |
| `guild_sync/ah_service.py` | `guild/ah_service.py` |
| `guild_sync/ah_sync.py` | `guild/ah_sync.py` |
| `guild_sync/attendance_processor.py` | `guild/attendance_processor.py` |
| `guild_sync/drift_scanner.py` | `guild/drift_scanner.py` |
| `guild_sync/integrity_checker.py` | `guild/integrity_checker.py` |
| `guild_sync/mitigations.py` | `guild/mitigations.py` |
| `guild_sync/reporter.py` | `guild/reporter.py` |
| `guild_sync/sync_logger.py` | `guild/sync_logger.py` |
| `guild_sync/rules.py` | `guild/rules.py` |
| `guild_sync/matching_rules/` | `guild/matching_rules/` |
| `guild_sync/migration.py` | `guild/migration.py` |
| `guild_sync/onboarding/` | `guild/onboarding/` |
| `guild_sync/api/routes.py` | `guild/api/routes.py` |
| `guild_sync/api/crafting_routes.py` | `guild/api/crafting_routes.py` |
| `identity/ranks.py` | `identity/ranks.py` |
| `identity/members.py` | `identity/members.py` |
| `identity/characters.py` | `identity/characters.py` |
| `discord/bot.py` | `discord/bot.py` |
| `discord/channel_sync.py` | `discord/channel_sync.py` |
| `discord/role_sync.py` | `discord/role_sync.py` |
| `discord/voice_attendance.py` | `discord/voice_attendance.py` |
| `db/models.py` | `db/models.py` |
| `db/seed.py` | `db/seed.py` |

### 2.3 — Move Guild-Specific config_cache Getters

Create or extend `src/guild_portal/config_cache.py`:
- Move `get_guild_name()`, `get_home_realm_slug()`, `get_realm_display_name()`, `get_guild_color()` (and any other guild-specific getters) out of sv_common's `config_cache.py` into this file.
- Import the generic `get()` helper from sv-common's `config_cache` as the backing store.

### 2.4 — Update All Imports in guild_portal

Do a global find-and-replace across `src/guild_portal/`:

| Old import | New import |
|------------|------------|
| `from sv_common.guild_sync.X import Y` | `from guild_portal.guild.X import Y` |
| `from sv_common.identity.X import Y` | `from guild_portal.identity.X import Y` |
| `from sv_common.discord.bot import ...` | `from guild_portal.discord.bot import ...` |
| `from sv_common.discord.channel_sync import ...` | `from guild_portal.discord.channel_sync import ...` |
| `from sv_common.discord.role_sync import ...` | `from guild_portal.discord.role_sync import ...` |
| `from sv_common.discord.voice_attendance import ...` | `from guild_portal.discord.voice_attendance import ...` |
| `from sv_common.db.models import ...` | `from guild_portal.db.models import ...` |
| `from sv_common.db.seed import ...` | `from guild_portal.db.seed import ...` |
| `from sv_common.config_cache import get_guild_name` (etc.) | `from guild_portal.config_cache import get_guild_name` (etc.) |

### 2.5 — Verify

- [ ] Run the full PATT test suite — all tests pass
- [ ] Start the PATT server locally; confirm no import errors on startup
- [ ] `sv_common/guild_sync/`, `sv_common/identity/`, and guild-specific discord modules are now dead code — do not delete yet (wait until SV-3 is wired up)

---

## Phase SV-3: Wire PATT to the sv-common Package

> **Repo:** `PullAllTheThings-site`
> **Prerequisite:** SV-1 complete (v1.0.0 tagged) and SV-2 complete

### 3.1 — Add sv-common as a Dependency

Add to PATT's `requirements.txt` (or `pyproject.toml` if it has one):

```
sv-common[discord] @ git+https://github.com/Shadowedvaca/sv-common@v1.0.0
```

Install on dev machine:
```bash
pip install "sv-common[discord] @ git+https://github.com/Shadowedvaca/sv-common@v1.0.0"
```

### 3.2 — Update Imports in guild_portal That Still Reference sv_common Generic Modules

| Old import | New import |
|------------|------------|
| `from sv_common.auth.passwords import ...` | `from sv_common.auth.passwords import ...` *(unchanged — same package name)* |
| `from sv_common.auth.jwt import ...` | `from sv_common.auth.jwt import ...` — but **update call sites** for new signature |
| `from sv_common.auth.invite_codes import ...` | `from sv_common.auth.invite_codes import ...` — but **update call sites** for new signature |
| `from sv_common.db.engine import ...` | `from sv_common.db.engine import ...` *(unchanged)* |
| `from sv_common.crypto import ...` | `from sv_common.crypto import ...` *(unchanged)* |
| `from sv_common.errors import ...` | `from sv_common.errors import ...` *(unchanged)* |
| `from sv_common.feedback import ...` | `from sv_common.feedback import ...` *(unchanged)* |
| `from sv_common.config_cache import get, set, seed_cache` | `from sv_common.config_cache import get, set, seed_cache` *(unchanged)* |
| `from sv_common.discord.channels import ...` | `from sv_common.discord.channels import ...` *(unchanged)* |
| `from sv_common.discord.dm import ...` | `from sv_common.discord.dm import ...` *(unchanged)* |

The package name stays `sv_common` — only the source changes (from local directory to installed package). Most imports don't change at all. The only call-site updates are for the functions with new signatures (jwt, invite_codes, config_cache guild accessors).

### 3.3 — Update jwt.py Call Sites in guild_portal

Find all `create_access_token(...)` and `decode_access_token(...)` calls. Update to pass `secret_key` and `expires_minutes` explicitly:

```python
# Before
token = create_access_token(user_id, member_id, rank_level)

# After
settings = get_settings()
token = create_access_token(
    secret_key=settings.secret_key,
    user_id=user_id,
    expires_minutes=settings.jwt_expire_minutes,
    extra_claims={"member_id": member_id, "rank_level": rank_level},
)
```

### 3.4 — Update invite_codes Call Sites

```python
# Before (PATT)
code = generate_invite_code(db, player_id=player.id, created_by_id=user.id, expires_hours=72)

# After
code = generate_invite_code(
    db,
    owner_id=user.id,
    expires_hours=72,
    metadata={"player_id": player.id},
)
```

### 3.5 — Delete sv_common Subdirectory from PATT

- [ ] `git rm -r src/sv_common/`
- [ ] Verify: `python -c "import sv_common; print(sv_common.__file__)"` points to the installed package, not the deleted directory
- [ ] Run full test suite — all pass
- [ ] Commit and push

---

## Phase SV-4: Migrate satt (This Repo)

> **Repo:** `saltallthethings-site`
> **Prerequisite:** SV-1 complete (v1.0.0 tagged)

This is the highest-leverage migration for satt. satt's sv_common carries **~50 files of dead WoW guild code** that satt never uses and never should. After this phase, satt's backend becomes much cleaner.

### 4.1 — What satt Actually Uses from sv_common

Currently satt only touches three functions from sv_common:

```python
# src/satt/auth.py
from sv_common.auth.passwords import hash_password, verify_password

# src/satt/routes/auth.py
from sv_common.auth.passwords import hash_password, verify_password

# src/satt/routes/users.py
from sv_common.auth.passwords import hash_password, verify_password
```

That's it. Three files, one function pair. Everything else in `src/sv_common/` (guild_sync, identity, discord/bot.py, db/models.py, etc.) is dead weight that was never imported by satt's own code.

### 4.2 — Add sv-common Dependency

Add to `requirements.txt` (or wherever satt's dependencies live):

```
sv-common @ git+https://github.com/Shadowedvaca/sv-common@v1.0.0
```

Install:
```bash
pip install "sv-common @ git+https://github.com/Shadowedvaca/sv-common@v1.0.0"
```

### 4.3 — Verify Existing Imports Still Work

The three import sites use `from sv_common.auth.passwords import ...` — this import path is **unchanged**. The package name is the same; it just now comes from the installed package instead of the local directory.

No import changes needed in satt's application code.

### 4.4 — Fix the Broken jwt.py (No Longer satt's Problem)

satt's `src/sv_common/auth/jwt.py` has `from patt.config import get_settings` — a broken import that would crash if anyone tried to use it. satt's own `auth.py` reimplements JWT correctly and never calls sv_common's jwt.py, so this has been a silent bomb.

After deleting `src/sv_common/`, the bomb is gone. satt's own `satt/auth.py` handles all JWT logic and does not change.

### 4.5 — Delete src/sv_common/ from satt

```bash
git rm -r src/sv_common/
```

This removes:
- `auth/jwt.py` (broken import, never used by satt)
- `auth/invite_codes.py` (used in routes/auth.py — but satt's own code has this)
- `auth/passwords.py` (now comes from installed package)
- `discord/` (never used by satt)
- `identity/` (never used by satt)
- `guild_sync/` (never used by satt — ~20 files of WoW sync code)
- `db/models.py` (never used by satt — satt has its own models.py)
- `db/engine.py` (now comes from installed package — confirm satt uses this)

**Check before deleting:** Verify satt uses `sv_common.db.engine`:
```bash
grep -r "sv_common.db" src/satt/
```

If satt's `database.py` uses `from sv_common.db.engine import ...`, that import continues to work from the installed package.

### 4.6 — Update invite_codes Call Sites in satt

satt's `routes/auth.py` calls `generate_invite_code`. After installing sv-common v1.0.0, the function signature changes:

```python
# Before (old sv_common — PATT-style player_id)
# satt likely uses a slightly different form; check the actual call

# After (sv-common v1.0.0)
code = generate_invite_code(
    db,
    owner_id=current_user.id,
    expires_hours=48,
)
```

Locate the call: `grep -n "generate_invite_code" src/satt/routes/auth.py` and update accordingly.

### 4.7 — Run Tests

```bash
cd /opt/satt-platform
TEST_DATABASE_URL=postgresql+asyncpg://satt_user:SaltSalty7x@localhost:5432/satt_test_db \
  PYTHONPATH=src venv/bin/pytest src/satt/tests/ -v
```

All tests should pass. The sv_common import (`auth.passwords`) now resolves through the installed package.

### 4.8 — Deploy

```bash
ssh hetzner
cd /opt/satt-platform
git pull
source venv/bin/activate
pip install "sv-common @ git+https://github.com/Shadowedvaca/sv-common@v1.0.0"
sudo systemctl restart satt
sudo systemctl status satt
```

---

## Phase SV-5: Migrate shadowedvaca (Optional, Low Urgency)

> **Repo:** `shadowedvaca-site`
> **Status:** shadowedvaca already made the right call — its sv_common is shallow. This phase is clean-up only.

### 5.1 — What shadowedvaca Uses

Only `auth/passwords.py` (functionally identical to sv-common's). Everything else (JWT, invite codes, DB engine, ORM) is reimplemented in `sv_site/`.

### 5.2 — Steps (if pursued)

- [ ] Add `sv-common @ git+https://github.com/Shadowedvaca/sv-common@v1.0.0` to dependencies
- [ ] Delete `src/sv_common/` from shadowedvaca-site (it only has the shallow copy)
- [ ] Optionally update `sv_site/auth.py` to use sv-common's parameterized JWT:
  ```python
  from sv_common.auth.jwt import create_access_token, decode_access_token

  # In create_access_token wrapper:
  token = create_access_token(
      secret_key=settings.secret_key,
      user_id=user.id,
      expires_minutes=settings.jwt_expire_minutes,
      extra_claims={"username": user.username, "is_admin": user.is_admin},
  )
  ```
- [ ] Run tests, deploy

### 5.3 — Why It's Low Priority

shadowedvaca's standalone JWT is clean, tested, and working. The only gain from unifying it is removing a ~40-line implementation file. There's no divergence risk since shadowedvaca intentionally has different claims. Do this when it's convenient, not as a blocker.

---

## Execution Order Summary

```
SV-1 (new repo + package) ──┐
                             ├──→ SV-3 (wire PATT)  ──→ SV-5 (shadowedvaca, optional)
SV-2 (guild code in PATT) ──┘

SV-1 alone ──→ SV-4 (satt)    ← satt can migrate as soon as SV-1 is tagged
```

SV-2 and SV-3 must run sequentially (SV-2 before SV-3). SV-4 only depends on SV-1 — it can happen before SV-2 and SV-3 are done.

---

## Ongoing Governance (Post-Migration)

- All sv-common changes via PR in `sv-common` repo; require review before merge
- Tag every release: `v1.0.0`, `v1.1.0`, etc. Never install from `@main`
- Breaking changes: bump minor version (`v1.0.x` → `v1.1.0`), note in release notes
- To ship a fix to all consumers: one PR to sv-common → tag → each app opens a version bump PR
- Each app's deploy docs should note the pip install step when upgrading sv-common version

---

## Quick Verification Commands (Post-Migration, Per App)

```bash
# Confirm sv_common resolves to installed package, not a local dir
python -c "import sv_common; print(sv_common.__file__)"
# Expected: .../site-packages/sv_common/__init__.py

# Confirm no leftover local sv_common directory
ls src/sv_common/
# Expected: ls: cannot access 'src/sv_common/': No such file or directory

# satt: confirm only the right imports are in play
grep -r "sv_common" src/satt/
# Expected: only auth/passwords imports (and db/engine if used)
```
