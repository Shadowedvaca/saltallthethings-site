# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Podcast website and admin tools for *Salt All The Things* (a WoW podcast). Public landing page + authenticated admin pages for show scheduling, AI-powered episode processing, and joke management. Backed by a Cloudflare Worker API with KV storage.

## Tech Stack

- **Zero-build frontend:** Pure HTML5/CSS3/vanilla JS — no frameworks, no bundler, no transpilation
- **Hosting:** GitHub Pages (static files) + Cloudflare Workers (API)
- **Storage:** Cloudflare KV (production), localStorage (local dev fallback)
- **AI:** Anthropic Claude API and OpenAI API (keys stored client-side only)
- **CI/CD:** GitHub Actions deploys on push to `main`

## Local Development

Open HTML files directly in a browser. No build step, no dev server needed. The auth gate auto-skips when the `__PASSWORD_HASH__` placeholder hasn't been replaced. Data falls back to localStorage when `__API_URL__` is unreplaced.

## Deployment Pipeline

GitHub Actions (`.github/workflows/deploy.yml`) on push to `main`:
1. Hashes `ADMIN_PASSWORD` secret (SHA-256) → injects into `js/auth.js`
2. Replaces `__API_URL__` placeholder in `js/storage.js` and `js/site-config.js`
3. Deploys to GitHub Pages

**GitHub Secrets:** `ADMIN_PASSWORD`, `SATT_API_URL`

## Architecture

### Pages

| Page | File | Auth |
|------|------|------|
| Public landing | `index.html` | No |
| Show management | `show_management.html` | Yes |
| Configuration | `config.html` | Yes |
| Joke bank | `jokes.html` | Yes |

### JS Modules (object-based, not class-based)

All modules use the pattern: `const ModuleName = { init(), method(), _privateMethod() }`

- **`auth.js`** — SHA-256 password hashing, sessionStorage sessions (8h TTL), `X-Auth` header for API
- **`storage.js`** — In-memory cache with async write-back to Cloudflare Worker API. Debounces writes via dirty flags. Falls back to localStorage when no API URL configured
- **`ai-service.js`** — Claude/OpenAI integration for generating episode titles, summaries, and outlines from raw show notes
- **`show-engine.js`** — Episode scheduling: recording dates, release dates, rollout logic (launch date: March 3, 2026; 2 episodes per Tuesday post-launch)
- **`site-config.js`** — Centralized platform links and social URLs
- **`toast.js`** — Notification toasts

### Cloudflare Worker API (`cloudflare/worker.js`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | No | Health check |
| GET | `/data/:key` | Yes | Read data key |
| PUT | `/data/:key` | Yes | Write data key |
| GET | `/export` | Yes | Full data dump |
| PUT | `/import` | Yes | Bulk import |
| GET | `/public/episodes` | No | Released episodes (paginated: `?page=&limit=`) |
| GET | `/public/homepage` | No | YouTube video IDs |

Data keys: `config`, `ideas`, `jokes`, `showSlots`, `assignments`

Worker deployed separately via Wrangler (`cloudflare/wrangler.toml`), binds to KV namespace `SATT_DATA`.

### Transcription Scripts (`scripts/`)

- `transcribe.bat` — WhisperX batch transcription with speaker diarization
- `label-speakers.py` — Post-processes WhisperX output to label speakers
- Requires: Python 3, FFmpeg, HuggingFace token (in `scripts/secrets.bat`, see `.example`)

## CSS Conventions

- Dark fantasy/gaming aesthetic with CSS custom properties for theming
- Key colors: gold `#c8a84e`, ice `#4a9eff`, purple `#6b4c9a`, dark backgrounds `#050509`–`#1e1e38`
- Fonts: Cinzel (headings), DM Sans (body), JetBrains Mono (code)
- Spacing scale: `--space-xs` through `--space-3xl`
- Responsive breakpoint at 1024px

