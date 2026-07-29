# Development and Release Standard

This document is authoritative for progressing repository work through
implementation, review, integration, and release. `reference/work-management.md`
defines issue hierarchy, Project fields, status, and approval boundaries.
`docs/delivery.md` is the human-facing system description, and
`reference/git-cicd-workflow.md` contains operational environment detail.
Prompt workbooks and future pipelines may supply invocation context, but they
must not override these repository instructions.

## Delivery loop

1. Read the parent, selected ordered children, and relevant repository
   references before changing code.
2. Use one shared `codex/<slice-slug>` branch and cumulative draft pull request
   for the current delivery slice.
3. Move only the active child to `In progress`.
4. Implement the child, update tests, documentation, `VERSION`, and
   `docs/releases/X.Y.Z.md` when the release is affected.
5. Run focused checks while iterating, then the complete local and CI-equivalent
   validation required by `docs/delivery.md`.
6. Push the tested commit. After validation, deploy the explicit branch to the
   isolated development environment with `deploy-dev.yml` when required.
7. Record test, CI, development deployment, manual verification, and deviation
   evidence. Move the child to `In review` and wait for approval.
8. A failed manual check remains in the same child until fixed and revalidated.
9. After approval, move the child to `Done` and continue only with the next
   approved child.

## Integration and release

After all children selected for the slice are approved, review the complete
diff, validation, documentation, version, and release notes; update the
cumulative pull request; and obtain explicit merge approval. Merge through the
pull request. A push to `main` deploys the approved integration commit to test
through `deploy-test.yml`. Verify test before considering production.

Production tags use `prod-vX.Y.Z`. Tag only the exact tested `main` commit, and
obtain separate, explicit production-release approval immediately before
creating or pushing the tag. Report the tag, SHA, workflow result, health
checks, logs, and manual production verification.

The legacy branch-push production behavior remains an acknowledged transition
risk until the Foundation release work replaces it. It is not an authorized
release path.

Hotfixes keep the same evidence and approval boundaries. Any shortened test
path must be explicitly proposed, approved, documented with risk, and followed
by reconciliation of `main` and test.

Do not modify production, infrastructure, DNS, GitHub environments, or secrets
without specific approval for that action.
