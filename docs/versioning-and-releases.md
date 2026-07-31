# Versioning and GitHub Releases

`VERSION` is the single authoritative application version. It contains one
canonical semantic version in `X.Y.Z` form. FastAPI metadata, `/api/health`,
delivery workflows, release validation, the production tag, curated notes, and
the GitHub Release must all use that value.

## Version changes

- **Patch (`X.Y.Z`)**: backwards-compatible fixes, security corrections,
  operational changes, documentation changes, and hotfixes.
- **Minor (`X.Y.0`)**: backwards-compatible user-facing capability. Increment
  the minor segment and reset patch to zero.
- **Major (`X.0.0`)**: intentionally incompatible application, API, data, or
  operator contract. Increment the major segment and reset minor and patch.
- **Hotfix**: branch from the approved production base, make only the emergency
  correction, and use the next patch version. Any shortened validation path
  requires explicit approval and recorded reconciliation.
- **Rollback**: redeploy an already validated immutable tag when its data
  contract remains compatible. Never move or reuse a tag. If code or migrations
  must change to recover, create and validate a new patch version.

The first child in a release slice updates `VERSION`, copies
`docs/releases/TEMPLATE.md` to `docs/releases/X.Y.Z.md`, and replaces every
instructional line. Later children update that same note cumulatively from the
actual diff and validation evidence.

## Validation

Run:

```bash
python scripts/validate_release.py
```

Pull-request validation runs the same command with read-only repository
permissions. It does not publish a release. Validation rejects:

- a non-canonical semantic version;
- a missing or mismatched release-note filename or heading;
- a missing, duplicate, empty, or reordered required section;
- template instructions or placeholder markers;
- credential-shaped values, private keys, credential-bearing URLs, or database
  URLs; and
- a production tag that does not exactly equal `prod-v` plus `VERSION`.

Release notes must describe user-visible behavior, operational impact,
migrations, validation, rollback, and limitations without secret values or
internal connection details.

## Production tag and GitHub Release

After the exact `main` commit has passed isolated test and separate production
release approval is recorded, create the immutable tag:

```bash
git tag prod-vX.Y.Z <tested-main-commit>
git push origin prod-vX.Y.Z
```

The production workflow checks out the exact tag commit, confirms that it is
contained in `main`, validates the version/tag/notes contract, deploys and
verifies that exact commit, and only then invokes the separate GitHub Release
publisher. The reusable publisher receives only the verified tag and commit,
uses a job-scoped contents token, publishes only `docs/releases/X.Y.Z.md`, and
cannot read deployment secrets or run application deployment commands. A failed
or unapproved production deployment cannot create or update the Release.

Tags are permanent: never force-push, delete and recreate, or point an existing
release tag at a different commit. A workflow rerun may update the GitHub
Release record from the same validated tag and curated notes; it may not change
the tag target.
