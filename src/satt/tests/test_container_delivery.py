"""Static safety tests for container and pull-request delivery configuration."""

from pathlib import Path
import re

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILES = tuple(REPOSITORY_ROOT.glob("compose*.yaml"))
WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/pull-request-validation.yml"
DEV_WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/deploy-dev.yml"
TEST_WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/deploy-test.yml"
RELEASE_WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/publish-release.yml"
PROD_WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/deploy-prod.yml"
PROD_SCRIPT_PATH = REPOSITORY_ROOT / "scripts/production_deploy.sh"
PROD_NIGHTLY_BACKUP_PATH = (
    REPOSITORY_ROOT / "scripts/production_nightly_backup.sh"
)


def test_container_context_excludes_sensitive_and_unrelated_files():
    ignored = (REPOSITORY_ROOT / ".dockerignore").read_text(encoding="utf-8")
    for expected in (
        ".git",
        ".env",
        "*.xlsx",
        "settings-backup",
        "cloudflare-backup.json",
        ".production-assets",
        ".production-state",
    ):
        assert expected in ignored

    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY . " not in dockerfile
    assert "USER satt" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "requirements.lock" in dockerfile


def test_production_environment_and_state_are_not_trackable():
    ignored = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env.*" in ignored
    assert ".production-state/" in ignored
    assert ".production-assets/" in ignored


def test_production_nightly_backup_is_private_verified_and_bounded():
    source = PROD_NIGHTLY_BACKUP_PATH.read_text(encoding="utf-8")

    for required in (
        "satt-production-postgres",
        "--schema=satt",
        "pg_restore --list",
        "/opt/backups/satt-db/nightly",
        "-mtime +14",
        'test -z "${DATABASE_URL:-}"',
        "--env-file",
        "compose.production.yaml",
    ):
        assert required in source

    for forbidden in (
        "TEST_DATABASE_URL",
        "docker volume rm",
        "down --volumes",
        "postgresql://",
    ):
        assert forbidden not in source


def test_environment_example_contains_placeholders_only():
    values = {}
    for line in (
        (REPOSITORY_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    ):
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value

    assert values["DATABASE_URL"] == ""
    assert values["LEGACY_DATABASE_URL"] == ""
    assert values["SATT_DB_PASSWORD"] == ""
    assert values["GOOGLE_OAUTH_CLIENT_SECRET"] == ""
    assert values["GOOGLE_OAUTH_REFRESH_TOKEN"] == ""
    assert values["SECRET_KEY"].startswith("replace-with-")


def test_compose_files_embed_no_database_urls_or_production_address():
    assert COMPOSE_FILES
    forbidden_url = re.compile(r"postgres(?:ql)?(?:\+asyncpg)?://", re.IGNORECASE)
    for compose_path in COMPOSE_FILES:
        source = compose_path.read_text(encoding="utf-8")
        assert forbidden_url.search(source) is None, compose_path.name
        assert "5.78.114.224" not in source
        yaml.safe_load(source)


def test_nonproduction_compose_definitions_are_isolated():
    development = yaml.safe_load(
        (REPOSITORY_ROOT / "compose.development.yaml").read_text(encoding="utf-8")
    )
    test = yaml.safe_load(
        (REPOSITORY_ROOT / "compose.test.yaml").read_text(encoding="utf-8")
    )
    production = yaml.safe_load(
        (REPOSITORY_ROOT / "compose.production.yaml").read_text(encoding="utf-8")
    )

    assert development["name"] == "satt-development"
    for compose_name in ("compose.yaml", "compose.ci.yaml"):
        database_healthcheck = yaml.safe_load(
            (REPOSITORY_ROOT / compose_name).read_text(encoding="utf-8")
        )["services"]["database"]["healthcheck"]["test"][1]
        assert "postmaster.pid" in database_healthcheck, compose_name
        assert '= "1" && pg_isready' in database_healthcheck, compose_name
    assert development["services"]["app"]["image"] == "satt:development"
    assert (
        development["services"]["app"]["ports"][0]
        == "127.0.0.1:${SATT_APP_PORT:?SATT_APP_PORT is required}:8200"
    )
    assert (
        development["services"]["app"]["environment"][
            "ALLOW_NONPRODUCTION_EXTERNAL_SERVICES"
        ]
        == "false"
    )
    for credential in (
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "GOOGLE_OAUTH_REFRESH_TOKEN",
    ):
        assert development["services"]["app"]["environment"][credential] == ""
    assert test["name"] == "satt-test"
    assert test["services"]["app"]["image"] == "satt:test"
    assert (
        test["services"]["app"]["ports"][0]
        == "127.0.0.1:${SATT_APP_PORT:?SATT_APP_PORT is required}:8200"
    )
    assert (
        test["services"]["app"]["environment"]["ALLOW_NONPRODUCTION_EXTERNAL_SERVICES"]
        == "false"
    )
    for credential in (
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "GOOGLE_OAUTH_REFRESH_TOKEN",
    ):
        assert test["services"]["app"]["environment"][credential] == ""
    assert (
        development["volumes"]["satt_postgres"]["name"]
        != test["volumes"]["satt_postgres"]["name"]
    )
    assert set(production["services"]) == {"app", "database"}
    production_database = production["services"]["database"]
    assert production_database["container_name"] == "satt-production-database"
    assert production_database["image"] == "postgres:16-alpine"
    assert "ports" not in production_database
    assert production_database["volumes"] == [
        "satt_production_postgres:/var/lib/postgresql/data"
    ]
    assert "postmaster.pid" in production_database["healthcheck"]["test"][1]
    assert production["volumes"]["satt_production_postgres"]["name"] == (
        "satt-production-postgres"
    )
    assert production["volumes"]["satt_production_postgres"]["name"] not in {
        development["volumes"]["satt_postgres"]["name"],
        test["volumes"]["satt_postgres"]["name"],
    }
    production_app = production["services"]["app"]
    assert production_app["container_name"] == "satt-production-app"
    assert production_app["image"] == "${SATT_IMAGE:?SATT_IMAGE is required}"
    assert production_app["depends_on"] == {
        "database": {"condition": "service_healthy"}
    }
    assert production_app["environment"]["SATT_DB_HOST"] == "database"
    assert "DATABASE_URL" not in production_app["environment"]
    assert "extra_hosts" not in production_app
    assert production_app["networks"] == ["satt"]
    assert production_database["networks"] == ["satt"]


def test_entrypoint_validates_isolation_before_migrations():
    entrypoint = (REPOSITORY_ROOT / "scripts/container-entrypoint.sh").read_text(
        encoding="utf-8"
    )
    settings_validation = entrypoint.index("get_settings")
    migration = entrypoint.index("alembic upgrade head")
    application = entrypoint.index('exec "$@"')
    assert settings_validation < migration < application
    migration_environment = (REPOSITORY_ROOT / "src/satt/migrations/env.py").read_text(
        encoding="utf-8"
    )
    assert "async with connectable.begin() as connection:" in migration_environment
    assert "set -eu" in entrypoint


def test_alembic_bootstraps_version_table_schema_on_fresh_database():
    migration_environment = (REPOSITORY_ROOT / "src/satt/migrations/env.py").read_text(
        encoding="utf-8"
    )
    online_migration = migration_environment.split(
        "def do_run_migrations(connection):", 1
    )[1]
    assert online_migration.index("CREATE SCHEMA IF NOT EXISTS satt") < (
        online_migration.index("context.configure(")
    )


def test_pull_request_workflow_has_minimal_permissions_and_pinned_actions():
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    assert workflow["permissions"] == {"contents": "read"}
    assert "push:" not in source
    assert "workflow_dispatch:" not in source
    assert "select version_num from satt.alembic_version" in source
    assert "python scripts/validate_release.py" in source
    assert "Validate current release contract without publishing" in source
    assert "Exercise isolated migration rollback and recovery" in source
    assert "app alembic downgrade 0005" in source
    assert 'test "$revision" = "0005"' in source
    assert "app alembic upgrade head" in source
    assert 'test "$revision" = "0006"' in source
    assert "docker compose -f compose.ci.yaml up -d --wait app" in source
    assert "Exercise isolated production backup restore" in source
    assert "pg_dump --format=custom --schema=satt" in source
    assert "pg_restore --exit-on-error" in source
    assert "Exercise isolated runtime recovery after health mismatch" in source
    assert "COMMIT_SHA=recovery-prior" in source
    assert "COMMIT_SHA=recovery-candidate" in source
    assert "forced-health-mismatch" in source

    action_uses = re.findall(r"uses:\s*([^\s#]+)", source)
    assert action_uses
    for action in action_uses:
        revision = action.rsplit("@", 1)[1]
        assert re.fullmatch(r"[0-9a-f]{40}", revision)


def test_ci_database_helper_cannot_target_external_hosts():
    source = (REPOSITORY_ROOT / "scripts/ci_validation.py").read_text(encoding="utf-8")
    assert '{"127.0.0.1", "localhost"}' in source
    assert 'os.environ.get("GITHUB_ACTIONS") != "true"' in source
    assert '"TEST_DATABASE_URL": migration_url' in source
    assert '"DATABASE_URL": guard_url' in source
    assert '"current", "--check-heads"' in source
    test_fixture = (REPOSITORY_ROOT / "src/satt/tests/conftest.py").read_text(
        encoding="utf-8"
    )
    assert "ON CONFLICT (id) DO UPDATE" in test_fixture


def test_development_deploy_is_manual_immutable_and_isolated():
    source = DEV_WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    assert "pipefailo" not in source
    strict_mode_lines = [
        line.strip() for line in source.splitlines() if line.strip().startswith("set -")
    ]
    assert strict_mode_lines
    assert set(strict_mode_lines) == {"set -euo pipefail"}

    assert workflow["permissions"] == {"contents": "read"}
    assert "workflow_dispatch:" in source
    assert "branch:" in source
    assert "push:" not in source
    assert "environment: development" in source

    action_uses = re.findall(r"uses:\s*([^\s#]+)", source)
    assert action_uses
    for action in action_uses:
        revision = action.rsplit("@", 1)[1]
        assert re.fullmatch(r"[0-9a-f]{40}", revision)

    for required in (
        "DEV_HOST",
        "DEPLOY_SSH_KEY",
        "DEV_SSH_KNOWN_HOSTS",
        'sha="$(git rev-parse HEAD)"',
        'git checkout --detach "$deploy_sha"',
        'test "$(git rev-parse HEAD)" = "$deploy_sha"',
        "version=\"$(tr -d '\\r\\n' < VERSION)\"",
        "DEPLOY_VERSION: ${{ steps.release.outputs.version }}",
        "/opt/satt-platform",
        "http://127.0.0.1:8300/api/health",
        "https://dev.saltallthethings.com/api/health",
        'assert data["environment"]=="development"',
        'assert data["version"]==expected_version',
        "select version_num from satt.alembic_version",
        "satt.scripts.environment_smoke",
        "--expected-environment development",
        '--expected-version "$expected_version"',
        "Development migration verified at revision $revision",
        "status=$?",
        "trap - EXIT",
        'exit "$status"',
        "logs --no-color --tail 100 app database",
        "< /dev/null | gzip -c",
        "set -euo pipefail",
    ):
        assert required in source

    for forbidden in (
        "TEST_HOST",
        "PROD_HOST",
        "test.saltallthethings.com",
        "docker image prune",
    ):
        assert forbidden not in source


def test_registered_workflow_is_manual_development_only():
    source = (REPOSITORY_ROOT / ".github/workflows/deploy.yml").read_text(
        encoding="utf-8"
    )
    workflow = yaml.safe_load(source)

    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["on"] == {
        "workflow_dispatch": {
            "inputs": {
                "branch": {
                    "description": (
                        "Explicit codex/* branch to deploy to isolated development"
                    ),
                    "required": True,
                    "type": "string",
                }
            }
        }
    }
    assert "uses: ./.github/workflows/deploy-dev.yml" in source
    assert "branch: ${{ inputs.branch }}" in source
    for forbidden in (
        "push:",
        "main",
        "legacy-production",
        "STAGING_SSH_KEY",
        "STAGING_SSH_KNOWN_HOSTS",
        "git pull",
        "systemctl restart",
    ):
        assert forbidden not in source


def test_production_deploy_is_tag_only_immutable_and_recoverable():
    source = PROD_WORKFLOW_PATH.read_text(encoding="utf-8")
    deploy_script = PROD_SCRIPT_PATH.read_text(encoding="utf-8")
    nightly_backup = PROD_NIGHTLY_BACKUP_PATH.read_text(encoding="utf-8")
    combined = source + deploy_script + nightly_backup
    workflow = yaml.safe_load(source)

    assert workflow["on"] == {"push": {"tags": ["prod-v*"]}}
    assert workflow["permissions"] == {}
    assert "branches:" not in source
    assert "workflow_dispatch:" not in source

    deploy = workflow["jobs"]["deploy"]
    assert deploy["environment"] == "production"
    assert deploy["permissions"] == {"contents": "read"}
    assert deploy["outputs"] == {
        "release_sha": "${{ steps.release.outputs.sha }}",
        "release_tag": "${{ steps.release.outputs.tag }}",
    }
    publish = workflow["jobs"]["publish"]
    assert publish["needs"] == "deploy"
    assert publish["permissions"] == {"contents": "write"}
    assert publish["uses"] == "./.github/workflows/publish-release.yml"
    assert publish["with"] == {
        "release_sha": "${{ needs.deploy.outputs.release_sha }}",
        "release_tag": "${{ needs.deploy.outputs.release_tag }}",
    }

    action_uses = re.findall(r"uses:\s*([^\s#]+)", source)
    assert action_uses
    for action in action_uses:
        if action.startswith("./"):
            assert action == "./.github/workflows/publish-release.yml"
            continue
        revision = action.rsplit("@", 1)[1]
        assert re.fullmatch(r"[0-9a-f]{40}", revision)

    for required in (
        "PROD_HOST",
        "DEPLOY_SSH_KEY",
        "PROD_SSH_KNOWN_HOSTS",
        "python scripts/validate_release.py",
        '--tag "$GITHUB_REF_NAME"',
        'test "$sha" = "$tag_sha"',
        'git merge-base --is-ancestor "$sha" origin/main',
        "main:refs/remotes/origin/main",
        'git checkout --detach "$deploy_tag"',
        'test "$(git rev-parse HEAD)" = "$deploy_sha"',
        "bash scripts/production_deploy.sh",
        "scripts/production_nightly_backup.sh",
        "rollback-cron",
        "-f compose.production.yaml",
        "python3 scripts/production_backup.py",
        '--phase "$phase"',
        "--schema=satt",
        "satt.scripts.production_fingerprint",
        'test "$source_state" = "$restored_state"',
        'test "$source_state" = "$post_state"',
        "pg_restore --exit-on-error",
        "alembic current --check-heads",
        'status="$?"',
        "trap - EXIT",
        'exit "$status"',
        "< /dev/null",
        "systemctl stop",
        "systemctl start",
        'git checkout --detach "$previous_sha"',
        "docker logs --tail 100 satt-production-app",
        'data["environment"]=="production"',
        "https://saltallthethings.com/api/health",
        "set -euo pipefail",
    ):
        assert required in combined

    for forbidden in (
        "DEV_HOST",
        "TEST_HOST",
        "STAGING_SSH_KEY",
        "STAGING_SSH_KNOWN_HOSTS",
        "git pull",
        "docker image prune",
        "compose.yaml",
        "compose.test.yaml",
        "compose.development.yaml",
        "docker volume rm",
        "down --volumes",
    ):
        assert forbidden not in combined

    preflight = deploy_script.index('preflight_backup="$(')
    build = deploy_script.index("compose build --pull app")
    stop = deploy_script.index('systemctl stop "$systemd_service"')
    final = deploy_script.index('final_backup="$(')
    restore = deploy_script.index("pg_restore --exit-on-error")
    start = deploy_script.index("compose up -d --wait --remove-orphans app")
    static = deploy_script.index('mv "$candidate_static" "$repository/static"')
    public = deploy_script.index("https://saltallthethings.com/api/health")
    assert preflight < build < stop < final < restore < start < static < public

def test_test_deploy_uses_only_the_approved_main_commit_and_isolated_test():
    source = TEST_WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)

    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["on"] == {"push": {"branches": ["main"]}}
    assert "workflow_dispatch:" not in source
    assert "environment: test" in source
    assert 'test "$GITHUB_REF" = "refs/heads/main"' in source
    assert 'test "$sha" = "$GITHUB_SHA"' in source

    action_uses = re.findall(r"uses:\s*([^\s#]+)", source)
    assert action_uses
    for action in action_uses:
        revision = action.rsplit("@", 1)[1]
        assert re.fullmatch(r"[0-9a-f]{40}", revision)

    for required in (
        "TEST_HOST",
        "DEPLOY_SSH_KEY",
        "TEST_SSH_KNOWN_HOSTS",
        'git checkout --detach "$deploy_sha"',
        'test "$(git rev-parse HEAD)" = "$deploy_sha"',
        "version=\"$(tr -d '\\r\\n' < VERSION)\"",
        "DEPLOY_VERSION: ${{ steps.release.outputs.version }}",
        "/opt/satt-platform",
        "-f compose.test.yaml",
        "http://127.0.0.1:8300/api/health",
        "https://test.saltallthethings.com/api/health",
        'assert data["environment"]=="test"',
        'assert data["version"]==expected_version',
        "select version_num from satt.alembic_version",
        "satt.scripts.environment_smoke",
        '--expected-version "$expected_version"',
        "status=$?",
        "trap - EXIT",
        'exit "$status"',
        "logs --no-color --tail 100 app database",
        "< /dev/null | gzip -c",
        "set -euo pipefail",
    ):
        assert required in source

    for forbidden in (
        "DEV_HOST",
        "PROD_HOST",
        "dev.saltallthethings.com",
        "https://saltallthethings.com/api/health",
        "docker image prune",
    ):
        assert forbidden not in source


def test_canonical_guidance_matches_current_production_gate():
    canonical_paths = (
        REPOSITORY_ROOT / "reference/ai-context.md",
        REPOSITORY_ROOT / "reference/development-and-release.md",
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in canonical_paths)
    assert "legacy push-to-`main` production workflow remains" not in combined
    assert "legacy branch-push production behavior remains" not in combined
    assert (
        "ordinary branch pushes and merges cannot deploy production" in combined.lower()
    )

    versioning = (REPOSITORY_ROOT / "docs/versioning-and-releases.md").read_text(
        encoding="utf-8"
    )
    normalized_versioning = " ".join(versioning.split())
    assert (
        "only then invokes the separate GitHub Release publisher"
        in normalized_versioning
    )
    assert (
        "A failed or unapproved production deployment cannot create"
        in normalized_versioning
    )


def test_release_workflow_runs_only_after_verified_production():
    source = RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)

    assert "push:" not in source
    call = workflow["on"]["workflow_call"]
    assert set(call["inputs"]) == {"release_sha", "release_tag"}
    for value in call["inputs"].values():
        assert value["required"] is True
        assert value["type"] == "string"
    assert workflow["permissions"] == {"contents": "write"}
    assert "environment: production" not in source
    assert "python scripts/validate_release.py" in source
    assert '--tag "$RELEASE_TAG"' in source
    assert 'test "$(git rev-parse HEAD)" = "$RELEASE_SHA"' in source
    assert 'test "$(git rev-list -n 1 "$RELEASE_TAG")" = "$RELEASE_SHA"' in source
    assert 'git merge-base --is-ancestor "$RELEASE_SHA" origin/main' in source
    assert 'gh release create "$RELEASE_TAG"' in source
    assert 'gh release edit "$RELEASE_TAG"' in source
    assert '--notes-file "$RELEASE_NOTES"' in source

    action_uses = re.findall(r"uses:\s*([^\s#]+)", source)
    assert action_uses
    for action in action_uses:
        revision = action.rsplit("@", 1)[1]
        assert re.fullmatch(r"[0-9a-f]{40}", revision)

    for forbidden in (
        "PROD_HOST",
        "DEPLOY_SSH_KEY",
        "ssh ",
        "docker compose",
    ):
        assert forbidden not in source
