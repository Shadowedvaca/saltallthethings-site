# Late-Bound Versions and GitHub Releases

Delivery contexts use `Version: Unassigned` through development, merge, and
successful test validation. The checked-in `VERSION` file contains
`unassigned`, which is also the default runtime identity outside production.

## Production version authority

- Mike alone selects the exact production tag. AI never invents, infers,
  calculates, increments, or recommends it from repository state, issues,
  metadata, semantic-version convention, or prior tags.
- The immutable `prod-vX.Y.Z` tag is the production-version authority.
- Production derives `X.Y.Z` from that tag and supplies it as `SATT_VERSION` to
  the unchanged exact tested commit.
- FastAPI metadata, `/api/health`, deployment verification, and the GitHub
  Release must report the tag-derived version.
- Hotfix and rollback version decisions remain Mike's. Tags are immutable; code
  or migration changes require another tested commit and new Mike-selected tag.

## Pending release records

Each delivery context creates one uniquely named
`docs/releases/pending/<context>.md` from `docs/releases/TEMPLATE.md`. The name
identifies the context rather than reserving a version. Concurrent contexts must
not edit the same pending record.

The record is cumulative for its Parent or Child delivery slice and is
reconciled after every child, before Promotion to test, and after exact-SHA test
validation. It describes shipped behavior, operational impact, migrations,
validation, rollback, and limitations without secrets or internal connection
details.

Historical `docs/releases/X.Y.Z.md` files remain immutable records of releases
created under the earlier source-versioned process.

## Validation

Run:

```bash
python scripts/validate_release.py
```

Development validation requires `VERSION` to remain `unassigned` and validates
the template, every historical versioned note, and every pending record. A
production selection additionally requires a canonical tag and a safe existing
path directly under `docs/releases/pending/`.

## Combined production gate

After the exact `main` candidate passes isolated test and any Release-timed
manual validation, AI verifies and reports current deployed production, valid
repository tags, the candidate SHA and PR, test evidence, selected pending
record, rollback readiness, and material risk. It then asks Mike for the exact
new production tag and approval to create it and deploy now in one question.

The approved tag is annotated with exactly one release-record trailer:

```bash
git tag -a prod-vX.Y.Z <tested-main-commit> \
  -m "Salt All The Things X.Y.Z" \
  -m "Release-Record: docs/releases/pending/<context>.md"
git push origin prod-vX.Y.Z
```

The production workflow checks out the exact tag commit, confirms main ancestry
and successful `deploy-test.yml` evidence for that same SHA, derives the runtime
version from the tag, and validates the selected pending record. It passes the
tag-derived version to production without changing the commit. Only after
deployment and public verification succeed does the least-privilege publisher
render the selected record with the release version and publish the GitHub
Release.

Never move, reuse, force-push, delete, or recreate a production tag. Ask for a
new approval if the tag, candidate SHA, selected record, evidence, deployment
mechanism, or required mutation changes after approval.
