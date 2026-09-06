# Salt All The Things — Shared AI Context

This file is authoritative for project identity, architecture, non-obvious
constraints, and durable repository guardrails. Work lifecycle and approvals
live in `reference/work-management.md`; quality, environments, deployments,
versions, release notes, database safety, secrets, backups, and rollback live in
`reference/development-and-release.md`.

## Delivery contexts, branches, and worktrees

The durable isolation invariant is:

> **One active delivery context = one parent or approved delivery slice + one
> Integration Cadence + one feature branch + one dedicated worktree + one
> cumulative pull request.**

A delivery context includes its selected and ordered children, User Validation
Timing, approved baseline, branch, worktree, pull request, pending release
record, validation history, and integration decision. Under Parent cadence one
context may own every selected child; a dedicated worktree does not impose a
separate branch, worktree, or approval per child.

Every new delivery context starts with `Version: Unassigned`. The exact
production version is not selected, reserved, inferred, or proposed while
building the prompt or starting the context. It remains unassigned through
development, Promotion to test, merge, and successful test validation.

### Worktree ownership

- Do not implement directly on `main`.
- Assign each new delivery context a uniquely named feature branch and dedicated
  worktree. Use `.worktrees/<context-slug>` under the primary checkout unless an
  explicitly approved workspace location is supplied. Keep them attached until
  the context is merged or abandoned.
- Do not switch an active worktree to `main`, another feature branch, or another
  context's branch, even temporarily.
- Do not borrow a worktree for an unrelated fix, review, experiment, or release.
- Concurrent parents or independent slices use separate worktrees. Selected
  children under Parent cadence accumulate in their shared context.
- Preserve unrelated branches, worktrees, and changes. Worktree cleanup is not
  permission to delete unmerged or unpublished work.

### Startup and resumption invariant

Before planning, editing, validating, committing, or operating on a delivery
context, verify:

1. the repository and top-level directory are SATT;
2. the physical worktree is assigned to the expected parent or slice;
3. the current branch and pull request belong to that context;
4. the working tree and index are clean, or every change is understood and
   belongs to the context;
5. the approved baseline and the branch relationships to its remote and
   `origin/main` are understood; and
6. no other branch, worktree, or pull request competes for the same context.

Fetch remote references when current remote knowledge is required; fetching is
read-only and does not authorize integration. A stale local `main` is evidence,
not authority to switch, reset, clean, merge, or rebase. Never silently absorb a
newer `origin/main` into an active context. Stop when ownership is competing,
ambiguous, or partially established rather than repairing it in place.

If upstream changes overlap the context's code, schemas, migrations, generated
artifacts, dependencies, CI/CD, configuration, release behavior, or canonical
instructions, report the impact and obtain approval before synchronization when
it would materially change scope, completed work, or delivery risk. Record the
chosen integration point and rerun the complete applicable gate afterward.

### Prompt-builder boundary

A prompt-builder workbook is a maintained generator, not ordinary execution
context. Its generated prompt must contain every run selection and instruction
needed by the AI. Do not open, inspect, or infer delivery context from a workbook
unless workbook maintenance or validation is explicitly authorized. Repository
policy remains authoritative when generated text is stale or incomplete.

Prompt construction records `Version: Unassigned`; it must not contain a
planned production tag.

### GitHub authentication on Mike's Windows host

GitHub CLI credentials are stored in the Windows keyring. A sandboxed command
may report an invalid token, private-Project 404, `unknown owner type`, or a
similar authentication symptom even when the host credential is valid.

1. Treat a sandbox-only failure as inconclusive.
2. Retry the required scoped `gh` operation through the approved host-level
   execution path.
3. Check `gh auth status` there if authentication still needs confirmation.
4. Ask Mike to authenticate only if the host-level result proves the credential
   is absent, invalid, or lacks the required scope.

Prefer the connected GitHub integration where it supports the operation. Use
host-level `gh` for unsupported operations such as Project fields and native
parent/sub-issue relationships, then verify the mutation. Never request or
expose a token in chat, commands, logs, issues, or repository files.

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
