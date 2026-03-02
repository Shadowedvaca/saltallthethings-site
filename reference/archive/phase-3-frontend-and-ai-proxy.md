# Phase 3 — Frontend Rewrites + AI Proxy

## Goal
Rewrite the three frontend JS modules that touch auth and data (`auth.js`, `storage.js`,
`ai-service.js`), implement the AI proxy endpoints in FastAPI, and add the invite code
generation UI. By the end of this phase the site runs fully end-to-end against the
Hetzner backend at `salt.shadowedvaca.com`. GitHub Pages is still live — this phase
runs in parallel, not as a cutover.

## Deliverables
- [ ] `auth.js` rewritten — JWT login flow, same gate UI
- [ ] `storage.js` rewritten — calls Hetzner API, JWT in Authorization header
- [ ] `ai-service.js` rewritten — calls FastAPI proxy, not Anthropic/OpenAI directly
- [ ] `POST /api/ai/process-idea` endpoint implemented and tested
- [ ] `POST /api/ai/generate-jokes` endpoint implemented and tested
- [ ] Invite code generation UI added to `config.html`
- [ ] GitHub Actions deploy workflow updated — string injection removed
- [ ] Full smoke test on `salt.shadowedvaca.com`: all 4 pages work, Rocket can log in
- [ ] `pytest` passes for AI proxy routes

---

## Repo Structure to Add

```
src/satt/
└── routes/
    └── ai.py               ← AI proxy endpoints

saltallthethings-site/
└── js/
    ├── auth.js             ← rewritten (JWT flow)
    ├── storage.js          ← rewritten (Hetzner API + JWT)
    └── ai-service.js       ← rewritten (proxy calls)
```

---

## Server Context

- **Staging URL:** `salt.shadowedvaca.com`
- **API base URL:** `https://salt.shadowedvaca.com/api` (hardcoded after this phase —
  no more `__API_URL__` placeholder)
- **PYTHONPATH:** `/opt/satt-platform/src`
- **Shared package:** `sv_common` in `src/sv_common/` — do not modify
- **Auth:** JWT from `sv_common.auth` — `Authorization: Bearer <token>` header
- **Port:** `8200`

---

## Part 1 — AI Proxy Endpoints (FastAPI)

AI API keys are stored in `satt.config` (set by the user in `config.html`). They
never leave the server. The browser sends the request to your FastAPI, FastAPI
calls Anthropic or OpenAI, returns the result.

### New environment variable

```
# .env
AI_REQUEST_TIMEOUT=60    # seconds before giving up on upstream AI call
```

### POST /api/ai/process-idea

**Auth:** Required (JWT)

**Request body:**
```json
{
  "rawNotes": "Rocket's raw notes for this episode..."
}
```

**Behavior:**
1. Load config from `satt.config`
2. Determine active AI model (`config.aiModel`: `"claude"` or `"openai"`)
3. Build system prompt and user prompt using the same logic as the current
   `ai-service.js` `_buildSystemPrompt()` and `_buildUserPrompt()` — replicate
   this logic server-side in Python exactly. The prompts use `config.showContext`,
   `config.segments`, and `config.titleCount`.
4. Call Anthropic or OpenAI API server-side using `httpx` (async)
5. Parse and validate the JSON response
6. Return result to browser

**Response:**
```json
{
  "titles": ["Title Option 1", "Title Option 2", "Title Option 3"],
  "summary": "A 2-3 sentence summary...",
  "outline": [
    {
      "segmentId": "opening",
      "segmentName": "Opening Hook / Intro",
      "talkingPoints": ["Point one", "Point two"]
    }
  ]
}
```

**Error handling:**
- `422` if `rawNotes` is empty
- `500` with `{"error": "AI API error: <message>"}` if upstream call fails
- `400` with `{"error": "No API key configured for <model>"}` if key is missing
  in config

---

### POST /api/ai/generate-jokes

**Auth:** Required (JWT)

**Request body:**
```json
{
  "themeHint": "housing"
}
```
`themeHint` is optional — empty string or omitted means general batch.

**Behavior:**
1. Load config from `satt.config`
2. Load existing used jokes from `satt.jokes` (status = `"used"`) to inject into
   the prompt as "already used — do not repeat"
3. Build joke system prompt using `config.jokeContext` and `config.jokeCount`
4. Call Anthropic or OpenAI server-side
5. Parse response — expect a JSON array of strings
6. Return jokes array

**Response:**
```json
{
  "jokes": ["Why did the WoW player...", "I asked my healer..."]
}
```

**Error handling:** Same pattern as `process-idea`.

---

### Prompt Builder (Python)

Create `src/satt/prompts.py` to hold the prompt construction logic:

```python
def build_process_idea_prompts(config: dict, raw_notes: str) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt)"""

def build_generate_jokes_prompts(config: dict, used_jokes: list[str], theme_hint: str) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt)"""
```

Replicate the exact prompt text from `js/ai-service.js` `_buildSystemPrompt()`,
`_buildUserPrompt()`, and the joke system prompt. Do not paraphrase — copy the
logic exactly so AI output is consistent before and after migration.

---

### AI Client (Python)

Create `src/satt/ai_client.py`:

```python
async def call_claude(system_prompt: str, user_prompt: str, config: dict) -> str:
    """Calls Anthropic API, returns raw text response."""

async def call_openai(system_prompt: str, user_prompt: str, config: dict) -> str:
    """Calls OpenAI API, returns raw text response."""

async def call_ai(system_prompt: str, user_prompt: str, config: dict) -> str:
    """Dispatches to call_claude or call_openai based on config.aiModel."""
```

Use `httpx.AsyncClient` with timeout from `AI_REQUEST_TIMEOUT` env var.
Do NOT use the Anthropic or OpenAI Python SDKs — use raw httpx calls to keep
the dependency footprint minimal and consistent with the existing JS approach.

**Anthropic endpoint:** `https://api.anthropic.com/v1/messages`
**OpenAI endpoint:** `https://api.openai.com/v1/chat/completions`

---

### Tests for AI Proxy

```
src/satt/tests/
├── test_ai_process_idea.py     ← mock httpx, verify prompt construction + response parsing
└── test_ai_generate_jokes.py   ← mock httpx, verify used jokes injected into prompt
```

Mock the upstream AI calls with `respx` or `pytest-httpx`. Do not make real API
calls in tests.

---

## Part 2 — Frontend JS Rewrites

### auth.js — Full Rewrite

**Same gate UI.** The HTML in `jokes.html`, `show_management.html`, and `config.html`
does not change. Only `auth.js` internals change.

**New flow:**
```
User enters password
  → POST /api/auth/login  {username, password}
    → 200: {access_token, token_type}  ← store in sessionStorage
    → 401: show "Wrong password" error (same shake animation)

Subsequent requests
  → Authorization: Bearer <access_token>

Session check on page load
  → if valid token in sessionStorage and not expired → skip gate
  → else → show gate

Logout
  → clear sessionStorage → reload (same as before)
```

**Key changes from old auth.js:**
- No more `__PASSWORD_HASH__` placeholder
- No more SHA-256 client-side hashing
- No more storing plaintext password in sessionStorage for X-Auth
- Token TTL: read from JWT expiry, not hardcoded 8h (but default to 8h if missing)
- Login endpoint: `POST /api/auth/login` (check PATT's sv_common.auth for exact
  endpoint path and request/response shape — match it exactly)

**Keep:**
- `Auth.init()` as the entry point called from each protected page
- `Auth.logout()` 
- `Auth._initStorage(loading)` pattern — called after successful auth, triggers
  `Storage.init()` then calls `onStorageReady()` if defined

**Dev mode:**
- If `window.location.hostname === 'localhost'` or `'127.0.0.1'` → skip gate,
  skip login call, set a fake token in sessionStorage
- Replaces the old `__PASSWORD_HASH__` dev mode detection

---

### storage.js — Full Rewrite

**Same public interface.** All callers (`show_management.html`, `jokes.html`,
`config.html`) call `Storage.getIdeas()`, `Storage.saveJokes()`, etc. — these
method signatures do not change. Only internals change.

**Key changes:**
- Remove `__API_URL__` placeholder — hardcode `https://salt.shadowedvaca.com/api`
  as the base URL (or read from a `const API_BASE` at top of file)
- Remove localStorage fallback entirely — server is always available
- Remove `migrateFromLocalStorage()` — migration is done, delete this
- Replace `X-Auth: password` header with `Authorization: Bearer <token>`
  (get token from `Auth.getToken()` — add this method to auth.js)
- `_pushToApi(key, value)` now calls `PUT /api/data/:key` with JWT header

**Keep:**
- In-memory cache pattern — all reads are synchronous from cache
- Debounced dirty flag write-back pattern
- All public getter/setter methods with identical signatures
- `Storage.init()` calls `GET /api/export` and populates cache

**New `Auth.getToken()` method** (add to auth.js):
```javascript
getToken() {
  try {
    const raw = sessionStorage.getItem(this._sessionKey);
    if (!raw) return null;
    const session = JSON.parse(raw);
    return session.token || null;
  } catch { return null; }
}
```

---

### ai-service.js — Targeted Rewrite

Replace only the API call methods. The prompt-building logic in `_buildSystemPrompt()`,
`_buildUserPrompt()`, and the joke system prompt are **deleted** — that logic now
lives server-side in `prompts.py`. The JS no longer needs it.

**New `processIdea()`:**
```javascript
async processIdea(rawNotes) {
  const token = Auth.getToken();
  const response = await fetch(`${API_BASE}/api/ai/process-idea`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({ rawNotes })
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.error || `AI error (${response.status})`);
  }
  return response.json();  // {titles, summary, outline}
}
```

**New `generateJokes()`:**
```javascript
async generateJokes(themeHint) {
  const token = Auth.getToken();
  const response = await fetch(`${API_BASE}/api/ai/generate-jokes`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({ themeHint: themeHint || '' })
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.error || `AI error (${response.status})`);
  }
  const data = await response.json();
  return data.jokes;  // string[]
}
```

**Delete from ai-service.js:**
- `_buildSystemPrompt()`
- `_buildUserPrompt()`
- `_callClaude()`
- `_callOpenAI()`
- `_callClaudeJokes()`
- `_callOpenAIJokes()`
- All references to `config.claudeApiKey`, `config.openaiApiKey`, `config.aiModel`

**Keep:**
- `_parseAIResponse()` — still used to validate the response from the proxy
- `_parseJokeResponse()` — same

---

### site-config.js — Minor Update

Remove the `__API_URL__` placeholder from `publicApiUrl`:

```javascript
// Before:
publicApiUrl: '__API_URL__',

// After:
publicApiUrl: 'https://salt.shadowedvaca.com/api',
```

No other changes.

---

## Part 3 — Invite Code Generation UI

Add to `config.html` — new card at the bottom of the page, inside the protected
content div.

**UI:**
```
┌─────────────────────────────────────┐
│ Invite Codes                        │
│                                     │
│ Generate a one-time invite link to  │
│ send to a new crew member.          │
│                                     │
│ [Generate Invite Code]  ← button    │
│                                     │
│ (after click, shows:)               │
│ ┌─────────────────────────────────┐ │
│ │ https://salt.shadowedvaca.com/  │ │
│ │ register?code=abc123            │ │
│ │                    [Copy Link]  │ │
│ └─────────────────────────────────┘ │
│ Expires in 48 hours. Send to Rocket.│
└─────────────────────────────────────┘
```

**Frontend call:**
```javascript
POST /api/auth/invite
Authorization: Bearer <token>
→ { "invite_url": "https://salt.shadowedvaca.com/register?code=abc123" }
```

Check `sv_common.auth` for the exact invite generation endpoint and response shape
— match it exactly. Do not invent a new endpoint.

**Register page (`register.html`):**
- New page, no auth gate
- Accepts `?code=abc123` query param
- Shows a simple form: username + password + confirm password
- `POST /api/auth/register` with `{invite_code, username, password}`
- On success: redirect to `index.html` with a toast "Account created. You can now
  log in."
- On error: show inline error (expired code, already used, etc.)

---

## Part 4 — Remove GitHub Actions String Injection

**File:** `.github/workflows/deploy.yml`

Remove these steps entirely:
- The step that hashes `ADMIN_PASSWORD` and injects it into `js/auth.js`
- The step that injects `SATT_API_URL` into `js/storage.js` and `js/site-config.js`

The deploy workflow after this phase should only:
1. Deploy static files to GitHub Pages (still active until Phase 4 cutover)

No secrets, no string replacement, no build step. The JS files now have real values
baked in.

---

## Staging Smoke Test Checklist

Before marking Phase 3 complete, verify all of the following against
`salt.shadowedvaca.com`:

**index.html (public)**
- [ ] Page loads, hero renders
- [ ] YouTube videos load (if configured)
- [ ] Platform links present

**Login flow**
- [ ] Password gate appears on `show_management.html`, `jokes.html`, `config.html`
- [ ] Wrong password shows error + shake
- [ ] Correct password logs in, gate dismisses, content loads
- [ ] Refresh keeps session