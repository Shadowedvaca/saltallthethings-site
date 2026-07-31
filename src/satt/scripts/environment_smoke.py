"""Run a non-production deployment smoke test without retaining credentials."""

from __future__ import annotations

import argparse
import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import delete

from satt.config import get_settings
from satt.database import get_session_factory
from satt.models import InviteCode, User

_ALLOWED_ENVIRONMENTS = {"development", "test"}
_PRODUCTION_HOSTS = {"saltallthethings.com", "www.saltallthethings.com"}
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}
_INVITE_CHARSET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


class SmokeFailure(RuntimeError):
    """A deployment smoke assertion failed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def validate_target(base_url: str, expected_environment: str) -> None:
    """Refuse production and cross-environment smoke targets."""
    settings = get_settings()
    hostname = urlparse(base_url).hostname

    _require(
        expected_environment in _ALLOWED_ENVIRONMENTS,
        "deployment smoke is restricted to development and test",
    )
    _require(
        settings.environment == expected_environment,
        "runtime environment does not match the requested smoke environment",
    )
    _require(
        settings.database_environment == expected_environment,
        "database ownership does not match the requested smoke environment",
    )
    _require(hostname not in _PRODUCTION_HOSTS, "production origins are forbidden")
    _require(
        hostname in _LOOPBACK_HOSTS,
        "deployment smoke may contact only the local application container",
    )
    _require(
        not settings.allow_nonproduction_external_services,
        "external-service opt-in must remain disabled during deployment smoke",
    )


async def _seed_invite(invite_code: str) -> None:
    factory = get_session_factory()
    async with factory() as session:
        session.add(
            InviteCode(
                code=invite_code,
                created_by_user_id=None,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            )
        )
        await session.commit()


async def _cleanup_identity(username: str, invite_code: str) -> None:
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(delete(User).where(User.username == username))
        await session.execute(
            delete(InviteCode).where(InviteCode.code == invite_code)
        )
        await session.commit()


def _expect_status(response: httpx.Response, expected: int, label: str) -> None:
    _require(
        response.status_code == expected,
        f"{label} returned HTTP {response.status_code}, expected {expected}",
    )


async def run_smoke(
    *,
    base_url: str,
    expected_environment: str,
    expected_version: str,
    expected_commit: str,
) -> None:
    """Exercise public, authentication, and protected API behavior."""
    validate_target(base_url, expected_environment)
    username = f"deploy-smoke-{secrets.token_hex(6)}"
    password = secrets.token_urlsafe(24)
    invite_code = "".join(secrets.choice(_INVITE_CHARSET) for _ in range(8))

    await _seed_invite(invite_code)
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
            health = await client.get("/api/health")
            _expect_status(health, 200, "health")
            health_data = health.json()
            _require(health_data.get("status") == "ok", "health status is not ok")
            _require(
                health_data.get("environment") == expected_environment,
                "health environment does not match",
            )
            _require(
                health_data.get("version") == expected_version,
                "health version does not match",
            )
            _require(
                health_data.get("commit") == expected_commit,
                "health commit does not match",
            )

            for path in ("/", "/register.html", "/public/homepage"):
                response = await client.get(path)
                _expect_status(response, 200, f"public route {path}")

            unauthorized = await client.get("/api/export")
            _expect_status(unauthorized, 401, "unauthenticated export")

            registration = await client.post(
                "/api/auth/register",
                json={
                    "username": username,
                    "password": password,
                    "inviteCode": invite_code,
                },
            )
            _expect_status(registration, 201, "registration")
            token = registration.json().get("token")
            _require(isinstance(token, str) and token, "registration returned no token")

            authenticated_export = await client.get(
                "/api/export",
                headers={"Authorization": f"Bearer {token}"},
            )
            _expect_status(authenticated_export, 200, "authenticated export")

            for attempt in (1, 2):
                login = await client.post(
                    "/api/auth/login",
                    json={"username": username, "password": password},
                )
                _expect_status(login, 200, f"login attempt {attempt}")
                login_token = login.json().get("token")
                _require(
                    isinstance(login_token, str) and login_token,
                    f"login attempt {attempt} returned no token",
                )
                reloaded_export = await client.get(
                    "/api/export",
                    headers={"Authorization": f"Bearer {login_token}"},
                )
                _expect_status(
                    reloaded_export,
                    200,
                    f"authenticated export attempt {attempt}",
                )
    finally:
        await _cleanup_identity(username, invite_code)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-environment", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()

    asyncio.run(
        run_smoke(
            base_url=args.base_url,
            expected_environment=args.expected_environment,
            expected_version=args.expected_version,
            expected_commit=args.expected_commit,
        )
    )
    print("Non-production deployment smoke passed; temporary identity removed.")


if __name__ == "__main__":
    main()
