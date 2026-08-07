# Salt All The Things — Shared AI Context

This file is authoritative for project identity, architecture, non-obvious
constraints, and durable repository guardrails. Work lifecycle and approvals
live in `reference/work-management.md`; quality, environments, deployments,
versions, release notes, database safety, secrets, backups, and rollback live in
`reference/development-and-release.md`.

## Workspace and repository guardrails

- Work in the primary checkout supplied by the workspace context. For this
  repository it is `H:\Development\saltallthethings-site`.
- Do not create a clone, linked worktree, implementation checkout, or durable
  deliverable outside that checkout without explicit approval for the exact
  location. Temporary tool output may use a scoped temporary directory.
- A dirty worktree is not permission to relocate, discard, or overwrite work.
  Preserve unrelated changes and continue in place when safe. If overlapping
  changes cannot be reconciled safely, stop and report the conflict.
- Before handoff, inspect `git status` and `git worktree list`. Confirm durable
  changes remain in the primary checkout; report older unrelated worktrees or
  recovery artifacts rather than moving or deleting them.
- Prompt workbooks and pipeline inputs provide invocation context only. They do
  not override repository instructions.

## Project identity

Salt All The Things (SATT) is the website and internal production toolkit for
the *Salt All The Things* World of Warcraft podcast at
`https://saltallthethings.com`. The repository contains the public site,
authenticated show-management tools, and the FastAPI backend that supports
them.

## Architecture

- **Frontend:** plain HTML, CSS, and JavaScript served without a framework,
  bundler, or build step. Browser calls use same-origin `/api` and `/public`
  paths.
- **Backend:** FastAPI and Uvicorn under `src/satt`, with async SQLAlchemy,
  Alembic migrations, and raw async `httpx` calls for upstream AI providers.
- **Database:** PostgreSQL with SATT-owned application tables and Alembic state.
- **Authentication:** JWT, bcrypt, invite registration, and user administration
  using the copied shared authentication components under `src/sv_common`.
- **Runtime:** one container image contains the explicitly public frontend and
  backend from the same commit and runs the application as an unprivileged user.
- **Delivery:** development, test, and production use isolated configuration
  and data. Operational details are intentionally centralized in
  `reference/development-and-release.md` and its linked runbooks.

Important locations:

| Path | Responsibility |
|---|---|
| `src/satt/main.py` | FastAPI application assembly and public static exposure. |
| `src/satt/routes/` | Health, authentication, data, AI, public, postproduction, Song Bank, Top 3, Guest Bank, and user routes. |
| `src/satt/models.py` / `src/satt/crud.py` | Core persistence model and data access. |
| `src/satt/*_contract.py` / `*_crud.py` | Feature-specific validation and persistence boundaries. |
| `src/satt/migrations/` | Alembic environment and ordered schema revisions. |
| `src/satt/tests/` | Backend, contract, delivery, security, and release tests. |
| `js/` | Browser storage, authentication, AI, show, postproduction, Song Bank, Top 3, Guest Bank, and UI modules. |
| Top-level `*.html` | Public and authenticated application pages. |
| `Dockerfile`, `compose*.yaml` | Shared image and environment-specific runtime definitions. |
| `.github/workflows/` | Pull-request validation and dev/test/prod/release automation. |

## Durable application contracts

### Frontend and API

- The frontend remains raw HTML/CSS/JS. Do not add a bundler or framework as an
  incidental implementation choice.
- Browser data contracts use camelCase. Backend serializers must not leak ORM
  snake_case into existing JavaScript contracts.
- Browser-generated opaque identifiers are stored as text. Do not regenerate,
  normalize, or reinterpret them server-side.
- The legacy generic data API uses full-array replacement where implemented;
  feature-specific endpoints add their own concurrency and integrity rules.
  Inspect current route and contract code before changing either behavior.
- Public routes are intentionally unauthenticated; private routes require JWT.
  Do not broaden static or API exposure accidentally.
- `js/show-engine.js` is pure schedule/date logic and has no storage or API
  dependency. Preserve that separation.

### AI and configuration

- The browser never calls Anthropic or OpenAI directly. Authenticated FastAPI
  routes proxy AI calls through `src/satt/ai_client.py` using raw `httpx`, not
  vendor Python SDKs.
- AI provider keys live server-side in SATT configuration. Browser responses
  expose only configured-status booleans, never key values.
- Blank key fields preserve existing server-side values; only an authenticated
  administrator may replace a stored key.
- AI tests mock upstream providers and must not consume real credentials.
- Prompt construction belongs in `src/satt/prompts.py`; preserve its explicit
  contracts and bounded repair behavior.

### Show outline contract

- Configured outline sections have stable unique IDs plus editable names,
  descriptions, and order. Renaming preserves identity; new sections receive
  new opaque IDs.
- A generated outline must include every configured section exactly once.
  Complete reordered output is normalized; missing, duplicate, unknown, or
  malformed output receives only the implemented bounded repair attempt and is
  rejected if still invalid.
- Each section contains two to five non-empty talking points.
- Configuration changes affect future generation only. Existing episode
  outlines are historical snapshots and are never silently rewritten.

### Shared code boundary

`src/sv_common` is copied from the Pull All The Things repository and resolved
through `PYTHONPATH`. Do not modify it here. A required shared change must be
made in the owning repository first and then propagated through the established
process.

## Durable safety boundaries

- SATT shares infrastructure with other sites. Never change or operate on
  another site's files, database, container, service, reverse-proxy
  configuration, DNS, or certificate.
- Do not expose the internal application port directly; public traffic passes
  through the configured reverse proxy.
- Do not expose repository metadata, backend source, environment files,
  workbooks, backups, or tests as public static assets.
- Do not store credentials in frontend code, repository files, release notes,
  issues, terminal output, or agent transcripts.
- Do not run database-backed tests without an explicit isolated test database.
  The test configuration must never resolve to production.
- Treat implemented behavior, tests, migrations, workflows, and validated
  runbooks as evidence. Do not document a capability merely because it is
  planned or desirable.

For database isolation, migrations, environment variables, secret handling,
backups, rollback, deployment, and release operations, follow
`reference/development-and-release.md` and the exact runbook it identifies.
