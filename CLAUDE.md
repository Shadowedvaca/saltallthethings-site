# Repository AI Entry Point

Codex and Claude Code use the same canonical repository instructions. Before
planning, editing, reviewing, or operating this repository, read these files in
order:

1. `reference/ai-context.md` for repository identity, durable boundaries,
   delivery-context isolation, and instruction authority.
2. `reference/work-management.md` for delivery slices, integration cadence,
   routine authority, stop conditions, human gates, evidence, and closure.
3. `reference/development-and-release.md` for environments, immutable
   promotion, late-bound version authority, release records, rollback, and
   release evidence.
4. `reference/testing-and-validation.md` for test selection, failure handling,
   technical evidence, and manual-validation boundaries.
5. `reference/testing-profile.md` for SATT's exact commands, layers, and
   evidence locations.
6. `MEMORY.md` for durable repository lessons. It is subordinate to the
   canonical policies under `reference/`.
7. Any additional references those documents identify for the active work.

The referenced files are authoritative. Keep model-specific execution details
out of this file, do not duplicate their procedures here, and update the
canonical reference instead when shared instructions change.

Prompt workbooks, generated prompts, and pipeline input provide invocation
context only; they do not override repository instructions. Preserve unrelated
user changes and stop to report any conflict that could risk data, issues,
releases, infrastructure, secrets, or production.
