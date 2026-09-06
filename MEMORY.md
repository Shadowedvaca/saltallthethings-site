# Repository Memory Boundary

This file contains durable repository context only. It is subordinate to the
user's explicit instructions and to the canonical reading order in
`AGENTS.md` and `CLAUDE.md`.

- One active delivery context owns one branch, one dedicated worktree, and one
  cumulative pull request. Parent cadence may include all selected children in
  that context; it does not require a separate worktree or approval per child.
- Parent-cadence child completion is an automatic technical checkpoint. Keep
  working through the ordered children unless a documented stop condition or
  the configured manual-validation timing applies.
- `In review` is reserved for a specific pending human action.
- A delivery context remains `Version: Unassigned` through development, merge,
  and successful test validation. Mike alone supplies the exact production tag.
- One combined production gate reports current production and candidate
  evidence and asks for both the exact new tag and deployment approval.
- The exact tested commit does not change when its production version is
  selected. Production derives its runtime version from the immutable tag and
  publishes the approved context-owned pending release record.
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
- GitHub CLI authentication stored in the Windows keyring may be unavailable to
  sandboxed commands. Follow `reference/ai-context.md` before asking Mike to
  authenticate again.
