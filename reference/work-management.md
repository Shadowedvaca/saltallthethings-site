# Work Management Standard

This document is authoritative for GitHub Project enrollment, issue hierarchy,
child expansion, delivery slices, branch and pull-request handling, approvals,
evidence, and closure. `reference/development-and-release.md` owns quality,
environment, version, deployment, and release rules.

## System of record

- GitHub issues are the source of truth for requirements, decisions,
  acceptance criteria, implementation evidence, and discussion.
- The private user Project **Solo Development** is the cross-repository planning
  view. Its fields organize work; they do not replace issue content.
- Use native GitHub parent/sub-issue relationships for hierarchy. A checklist
  may summarize children but is not a substitute for the native relationship.
- Repository labels describe repository-specific type or area when useful.
  Project Status, Priority, Size, Release, and Target date belong in Project
  fields rather than duplicate status labels.

## AI-created issue enrollment

Unless the user says otherwise or the issue is explicitly legacy, every issue
created by AI must be added to **Shadowedvaca / Solo Development**
(`projects/7`). Creation is not complete until the agent:

1. Creates the issue in the correct repository and captures its canonical URL.
2. Adds that exact issue URL to **Solo Development** through an authenticated
   GitHub integration, API, or `gh project item-add`.
3. Verifies that the issue appears in the Project exactly once.
4. Sets Project Status to `Inbox` unless the user or an approved active plan
   explicitly authorizes another state.
5. Adds the native parent/sub-issue relationship when the issue is a child.
6. Reports the URL, parent relationship when applicable, and verified Project
   enrollment.

If enrollment or field assignment fails, preserve the issue, report the exact
incomplete step and error, and retry safely or hand back the specific repair.
Do not delete and recreate the issue, create a duplicate, or silently continue.

## Status lifecycle

| Status | Meaning |
|---|---|
| `Inbox` | Captured but not yet triaged. |
| `Backlog` | Accepted work that is not yet ready to begin. |
| `Ready` | Scoped, ordered where necessary, and ready to begin. |
| `In progress` | Implementation is actively underway. |
| `In review` | Technical completion evidence is recorded and approval is pending. |
| `Done` | Approved and complete at the delivery stage required by the issue or slice. |
| `Not planned` | Declined, duplicate, obsolete, or intentionally not proceeding. |

Child completion does not imply parent completion or authorize integration or
release. Evaluate each issue and delivery stage independently.

## Work hierarchy

### Parent issues

A parent represents a durable outcome, feature area, or roadmap direction. It
provides shared context and the larger definition of done; it need not equal a
single delivery slice or release. Use these sections when applicable:

```markdown
## Goal
## Why this matters
## Child issues
## Scope
## Done when
## Guardrails
## Deferred
```

### Child issues

A child is the unit of implementation and individual completion approval. Use
these sections when applicable:

```markdown
## Goal
## Parent
## Implementation scope
## Acceptance criteria
## Testing and validation
## Documentation and release notes
## Dependencies or guardrails
## Completion evidence
```

### Controlled child expansion

Discovery that contributes to the same parent outcome may become an explicit
new child under the current parent. Do not create a new parent merely because
scope was discovered during implementation, and do not hide the work inside an
unrelated child.

Before implementing a material expansion:

1. Explain why existing children do not represent it.
2. State whether it is required for the current delivery slice or deferred.
3. Record scope, acceptance criteria, dependencies, release impact, and any
   ordering change.
4. Create and enroll the child, add the native parent relationship, and update
   the ordered child list.
5. Obtain approval for the material scope decision.

## External run inputs

Every run receives two independent controls. Record both with the selected
parent/children before implementation. Do not infer one from the other.

### User Validation Timing

`User Validation Timing` controls when a person must validate behavior through
the user interface. Its values are:

- `Child`: after each applicable child receives Child development complete
  approval, validate the prepared development artifact before that child's
  slice can promote to test.
- `Parent`: after every selected child receives Child development complete
  approval, validate the cumulative development artifact before the final
  applicable Promotion to test. This timing remains the same under either
  Integration Cadence.
- `Release`: after Promotion to test, validate the immutable test candidate
  before Promotion to production.

This control applies only to manual human UI validation. Automated browser
tests, API checks, database checks, health checks, scripts, and other
AI-executable verification are technical checks, not human approval gates. If
the change has no UI behavior to validate, record that manual UI validation is
not applicable rather than manufacturing a gate.

### Integration Cadence

`Integration Cadence` controls how selected children form releasable slices:

- `Parent` (default): all selected children share one cumulative branch and
  draft pull request. Each child is completed and approved individually, but
  the slice merges and promotes to test only after the final selected child and
  all manual validation required before that stage. Do not create a PR per
  child.
- `Child`: each child is its own releasable slice with its own branch, pull
  request, merge/test promotion, and exact Mike-selected version.

User Validation Timing and Integration Cadence solve different problems and
must never be conflated.

## Delivery slices, branches, and pull requests

- A delivery slice is the explicitly selected, ordered set of children that
  will integrate together under the chosen Integration Cadence.
- Use `codex/<slice-slug>` unless the approved work requires the repository's
  hotfix convention.
- Create and maintain a draft pull request as routine reversible work. Marking
  it ready is also routine once the technical evidence is complete; neither is
  a separate approval gate.
- Keep commits focused enough to review each child independently, while keeping
  one cumulative branch and PR for Parent cadence.
- Reconcile the cumulative diff, documentation, release note, and evidence
  after every child. A failed check remains with the same child until fixed and
  revalidated.
- Preserve unrelated work and do not relocate work from the supplied checkout
  merely because the worktree is dirty. Follow `reference/ai-context.md` for
  workspace guardrails.

## Authorization and approval gates

Routine authorized work proceeds without repeated permission requests. Within
the selected scope this includes repository inspection, implementation,
automated tests, formatting, linting, builds, API/health/database checks,
documentation, cumulative release-note maintenance, branch updates,
development artifacts, draft PR preparation, and other reversible technical
work.

There are four happy-path gate types. Their chronological position is
conditional only for manual UI validation:

1. **Child development complete.** Implementation, automated checks,
   documentation, cumulative release-note reconciliation, and technical
   evidence are complete. Summarize the result and wait for approval of that
   child before asking a person to perform UI validation.
2. **Manual human UI validation.** Stop only when User Validation Timing makes
   it due. For `Child` or `Parent`, this gate follows the applicable
   development-complete approval and uses the prepared development artifact
   before Promotion to test. For `Release`, it follows Promotion to test and
   uses the immutable test candidate before Promotion to production. Provide a
   concise UI checklist and wait for the user's results.
3. **Promotion to test.** The applicable delivery slice is complete, all human
   validation required before test has passed, and the PR is ready to merge.
   One approval authorizes merging that PR to `main` and allowing the resulting
   test CI/CD promotion. Do not create separate approval gates for opening the
   PR, marking it ready, merging, and allowing test CI/CD to run. Validation
   explicitly scheduled for `Release` occurs after this promotion and does not
   block the promotion that creates its test candidate.
4. **Promotion to production.** Test evidence, release reconciliation, and any
   Release-timed UI validation are complete. One approval authorizes creation
   of the exact Mike-selected production tag and allows production CI/CD to
   run.

Outside these gates, stop only for a genuine question, material scope decision,
unexpected risk, missing authority, destructive or irreversible action not
already covered by a gate, security concern, or blocker. Approval is scoped to
the stated gate; child completion never silently authorizes integration or
production.

## Evidence and closure

Before requesting child-completion approval, record:

- implemented behavior and important files changed;
- automated tests and quality checks, including results;
- CI and development artifact/deployment results when applicable;
- documentation and cumulative release-note changes;
- whether manual UI validation is applicable and when it will be due. Record
  results only after the development-complete approval and scheduled manual
  gate occur;
- risks, limitations, deviations, and focused follow-up work; and
- relevant commit, branch, PR, deployment, and workflow links or identifiers.

Move a child to `Done` only after its required approval and delivery stage are
complete. Close a parent only when its current definition of done is satisfied.
Clearly identify later work that remains under a durable parent.
