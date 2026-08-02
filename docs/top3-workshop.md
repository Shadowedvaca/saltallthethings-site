# Top 3 Concept Workshop and Bank

The authenticated Top 3 Bank at `/top3.html` is the shared workshop for reusable
Top 3 definitions. It is intentionally separate from episode idea outlines and
from every participant submission.

## Manual workflow

1. Enter the concept description and optionally provide a shared name, rules,
   host planning notes, and either zero or exactly three fictional examples.
2. Review the form and choose **Save Manually**.
3. Edit, filter, retire, restore, or delete the banked concept as needed.

## AI-assisted workflow

1. Enter a description and any optional context, then choose **Generate AI
   Proposal**.
2. Review and edit the returned shared name, description, rules, and three
   fictional examples. The examples are illustrative and never represent a
   host, guest, or listener submission.
3. Regenerate if needed, or explicitly choose **Save AI Proposal**. Generation
   alone never creates a bank record.
4. The accepted concept retains its server-generated provider, model, and
   generation timestamp provenance across later edits.

AI credentials remain server-side. The browser receives only proposal content
and non-secret provenance. Missing credentials, provider failures, invalid AI
responses, stale revision conflicts, and save failures remain visible without
discarding the current form so the user can correct or retry the action.

## Assignment state and lifecycle

Concept cards show the episode ideas currently using a concept, including an
episode number when the idea is scheduled. This metadata never includes ranked
picks or private discussion notes. Assigned concepts cannot be deleted. Retire
and restore remain reversible; deleting an unassigned concept is permanent.

The Top 3 Bank uses the dedicated `/api/top3/*` routes and its own in-memory
revision-aware cache. Top 3 concepts and submissions remain excluded from the
general export, import, and shared browser storage contracts.
