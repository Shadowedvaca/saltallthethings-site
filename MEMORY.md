# Repository Memory Boundary

This file contains durable repository context only. It is subordinate to the
user's explicit instructions and to the canonical reading order in
`AGENTS.md` and `CLAUDE.md`.

- Work in this repository checkout, never in a substitute clone or temporary
  project directory. Temporary directories may hold disposable test artifacts
  only.
- `AGENTS.md` and `CLAUDE.md` must remain byte-for-byte identical. Shared
  procedure belongs in the canonical `reference/` documents, not in either
  model-specific entry point.
- Do not record active issue status, branch names, selected versions, pending
  approvals, transient test results, deployment state, or other run-specific
  facts here. GitHub and the active work record own that state.
- Never store secrets, credentials, tokens, database URLs, private environment
  values, or secret-bearing configuration here. Verify sensitive configuration
  only through configured status, presence, or an approved one-way fingerprint.
- Prompt workbooks and invocation text provide run context; they do not
  override repository instructions or become a second source of truth.
