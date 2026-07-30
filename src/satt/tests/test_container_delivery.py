"""Static safety tests for container and pull-request delivery configuration."""

from pathlib import Path
import re

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILES = tuple(REPOSITORY_ROOT.glob("compose*.yaml"))
WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/pull-request-validation.yml"
DEV_WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/deploy-dev.yml"


def test_container_context_excludes_sensitive_and_unrelated_files():
    ignored = (REPOSITORY_ROOT / ".dockerignore").read_text(encoding="utf-8")
    for expected in (
        ".git",
        ".env",
        "*.xlsx",
        "settings-backup",
        "cloudflare-backup.json",
    ):
        assert expected in ignored

    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY . " not in dockerfile
    assert "USER satt" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "requirements.lock" in dockerfile


def test_environment_example_contains_placeholders_only():
    values = {}
    for line in (REPOSITORY_ROOT / ".env.example").read_text(
        encoding="utf-8"
    ).splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value

    assert values["DATABASE_URL"] == ""
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
        database_healthcheck = (
            yaml.safe_load((REPOSITORY_ROOT / compose_name).read_text(encoding="utf-8"))
            ["services"]["database"]["healthcheck"]["test"][1]
        )
        assert "postmaster.pid" in database_healthcheck, compose_name
        assert '= \"1\" && pg_isready' in database_healthcheck, compose_name
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
    assert development["volumes"]["satt_postgres"]["name"] != test["volumes"][
        "satt_postgres"
    ]["name"]
    assert "database" not in production["services"]


def test_entrypoint_validates_isolation_before_migrations():
    entrypoint = (
        REPOSITORY_ROOT / "scripts/container-entrypoint.sh"
    ).read_text(encoding="utf-8")
    settings_validation = entrypoint.index("get_settings")
    migration = entrypoint.index("alembic upgrade head")
    application = entrypoint.index('exec "$@"')
    assert settings_validation < migration < application
    migration_environment = (
        REPOSITORY_ROOT / "src/satt/migrations/env.py"
    ).read_text(encoding="utf-8")
    assert "async with connectable.begin() as connection:" in migration_environment
    assert "set -eu" in entrypoint


def test_alembic_bootstraps_version_table_schema_on_fresh_database():
    migration_environment = (
        REPOSITORY_ROOT / "src/satt/migrations/env.py"
    ).read_text(encoding="utf-8")
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

    action_uses = re.findall(r"uses:\s*([^\s#]+)", source)
    assert action_uses
    for action in action_uses:
        revision = action.rsplit("@", 1)[1]
        assert re.fullmatch(r"[0-9a-f]{40}", revision)


def test_ci_database_helper_cannot_target_external_hosts():
    source = (REPOSITORY_ROOT / "scripts/ci_validation.py").read_text(
        encoding="utf-8"
    )
    assert '{"127.0.0.1", "localhost"}' in source
    assert 'os.environ.get("GITHUB_ACTIONS") != "true"' in source
    assert '"TEST_DATABASE_URL": migration_url' in source
    assert '"DATABASE_URL": guard_url' in source
    assert '"current", "--check-heads"' in source
    test_fixture = (
        REPOSITORY_ROOT / "src/satt/tests/conftest.py"
    ).read_text(encoding="utf-8")
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
        "/opt/satt-platform",
        "http://127.0.0.1:8300/api/health",
        "https://dev.saltallthethings.com/api/health",
        'assert data["environment"]=="development"',
        'assert data["version"]=="0.0.1"',
        "logs --no-color --tail 100 app database",
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


def test_registered_legacy_workflow_bootstraps_development_safely():
    source = (REPOSITORY_ROOT / ".github/workflows/deploy.yml").read_text(
        encoding="utf-8"
    )
    workflow = yaml.safe_load(source)

    assert workflow["permissions"] == {"contents": "read"}
    assert "uses: ./.github/workflows/deploy-dev.yml" in source
    assert "branch: ${{ inputs.branch }}" in source
    assert "if: github.event_name == 'workflow_dispatch'" in source
    assert (
        "if: github.event_name == 'push' && github.ref == 'refs/heads/main'"
        in source
    )
