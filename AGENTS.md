# Salt All The Things — Codex Context

Read `CLAUDE.md` completely before making changes; its architecture, deployment, testing, and safety rules apply to Codex work.

## Secret Handling (STRICT)

- Never print or return API keys, tokens, passwords, private keys, OAuth secrets, database URLs, or secret-bearing configuration records.
- AI credentials remain server-side in `satt.config`. Browser responses may expose only boolean configured-status fields.
- Validate secrets only by presence or one-way SHA-256 fingerprint.
- Preserve stored secrets when an update omits them or submits a blank field. Only administrators may replace AI credentials.
- If a secret is exposed, stop and rotate it before continuing.

## Git and Deployment

- Work on feature branches; never commit directly to `main`.
- Preserve unrelated uncommitted changes.
- Do not deploy or run database-backed tests against production.
- Follow `docs/delivery.md` as the canonical branch, issue, approval, promotion,
  and production-permission contract.
- Foundation release work uses one shared `codex/<parent-issue-title-slug>`
  branch and one cumulative draft pull request, with children completed in their
  recorded order.
- A child approval authorizes only the next child. It does not authorize merge,
  test deployment, a production tag, production deployment, server or DNS
  changes, GitHub environment changes, or repository secret changes.
- Production requires a separately approved immutable `prod-vX.Y.Z` tag.
