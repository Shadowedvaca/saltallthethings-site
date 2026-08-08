# Versioning and GitHub Releases

`VERSION` is the single authoritative application version. It contains one
canonical semantic version in `X.Y.Z` form. FastAPI metadata, `/api/health`,
delivery workflows, release validation, the production tag, curated notes, and
the GitHub Release must all use that value.

## Version changes

- Mike is the sole authority for the exact version. AI must never invent,
  infer, calculate, increment, or replace it from GitHub state, issue wording,
  existing tags, metadata, or semantic-version convention.
- After Mike supplies the exact value, AI may write it to `VERSION`, update the
  matching release note, verify all repository-defined consumers, and report
  mismatches.
- Hotfix and rollback version decisions remain Mike's. Tags are immutable; a
  rollback may redeploy a compatible validated artifact, while changed code or
  migrations require another exact Mike-selected version.

Once Mike has selected the exact version, the first approved child in a release
slice creates the matching `docs/releases/X.Y.Z.md` from the template when it
does not exist, or updates the existing cumulative note. Later children
reconcile that same note against the actual cumulative diff and evidence.

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

After the exact `main` commit has passed isolated test, any Release-timed manual
UI validation has passed on that immutable candidate, and Promotion to
production approval is recorded, create the immutable tag:

```bash
git tag prod-vX.Y.Z <tested-main-commit>
git push origin prod-vX.Y.Z
```

The production workflow checks out the exact tag commit, confirms that it is
contained in `main`, validates the version/tag/notes contract, and queries the
GitHub Actions API for a completed successful `deploy-test.yml` push run on
`main` with the same exact SHA. It fails before SSH when that proof is absent.
It deploys and verifies that exact commit and only then invokes the separate
GitHub Release publisher. The reusable publisher receives only the verified
tag and commit, uses a job-scoped contents token, publishes only
`docs/releases/X.Y.Z.md`, and cannot read deployment secrets or run application
deployment commands. A failed or unapproved production deployment cannot
create or update the Release.

Tags are permanent: never force-push, delete and recreate, or point an existing
release tag at a different commit. A workflow rerun may update the GitHub
Release record from the same validated tag and curated notes; it may not change
the tag target.
