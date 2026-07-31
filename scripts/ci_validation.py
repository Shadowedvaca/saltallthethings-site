"""Run migration and database tests against a tightly constrained CI database."""

from __future__ import annotations

import os
import subprocess
import sys
from urllib.parse import quote


def _ci_database_url(database_name: str) -> str:
    host = os.environ.get("CI_DB_HOST", "")
    port = os.environ.get("CI_DB_PORT", "")
    user = os.environ.get("CI_DB_USER", "")
    password = os.environ.get("CI_DB_PASSWORD", "")

    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("This helper may run only in GitHub Actions")
    if host not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("CI database host must be loopback")
    if port != "5432" or user != "satt_ci":
        raise RuntimeError("Unexpected CI database identity")
    if database_name not in {"satt_ci", "satt_ci_guard"}:
        raise RuntimeError("Unexpected CI database name")
    if not password:
        raise RuntimeError("CI database password is required")

    return "postgresql+asyncpg://{}:{}@{}:{}/{}".format(
        quote(user, safe=""),
        quote(password, safe=""),
        host,
        port,
        quote(database_name, safe=""),
    )


def _run(command: list[str], environment: dict[str, str]) -> None:
    subprocess.run(command, env=environment, check=True)


def main() -> int:
    migration_url = _ci_database_url("satt_ci")
    guard_url = _ci_database_url("satt_ci_guard")
    base_environment = os.environ.copy()
    base_environment.update(
        {
            "ENVIRONMENT": "test",
            "DATABASE_ENVIRONMENT": "test",
            "SECRET_KEY": "ci-only-signing-placeholder-at-least-32-characters",
            "SITE_URL": "http://testserver",
            "CORS_ORIGINS": "http://testserver",
            "COMMIT_SHA": os.environ.get("GITHUB_SHA", "ci"),
            "ALLOW_NONPRODUCTION_EXTERNAL_SERVICES": "false",
            "GOOGLE_OAUTH_CLIENT_ID": "",
            "GOOGLE_OAUTH_CLIENT_SECRET": "",
            "GOOGLE_OAUTH_REFRESH_TOKEN": "",
        }
    )

    migration_environment = base_environment | {"DATABASE_URL": migration_url}
    _run([sys.executable, "-m", "alembic", "upgrade", "head"], migration_environment)
    _run(
        [sys.executable, "-m", "alembic", "current", "--check-heads"],
        migration_environment,
    )

    test_environment = base_environment | {
        "DATABASE_URL": guard_url,
        "TEST_DATABASE_URL": migration_url,
    }
    _run(
        [sys.executable, "-m", "pytest", "src/satt/tests", "-q"],
        test_environment,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
