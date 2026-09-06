# Salt All The Things — Pending Release

## Highlights

- AI delivery contexts can run a whole Parent slice automatically while independent contexts remain isolated for concurrent work.
- Production versions are selected only after the exact candidate passes test validation.

## Fixes/Changes

- Child development completion is now an automatic technical checkpoint under Parent cadence.
- Production derives its visible version from Mike's approved immutable tag instead of a version reserved in source.
- Every delivery context owns a uniquely named pending release record.

## Validation

- `python3 scripts/validate_repository_docs.py`, development and production-mode release validation, Python compilation, workflow YAML parsing, shell syntax checks, and production Compose validation pass.
- The available Python suite passes with 223 tests; 129 database-backed tests are safely skipped because no isolated `TEST_DATABASE_URL` is configured.

## Deployment/Migrations

- No database migration is required. Development and test report version `unassigned`; production receives the tag-derived version through runtime configuration.

## Rollback

- Application rollback continues to use a compatible previously validated artifact. Production tags remain immutable.

## Known Limitations

- Production promotions remain serialized even though development contexts may run concurrently.
