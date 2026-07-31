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


def _headers(token: str, revision: int | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if revision is not None:
        headers["If-Match"] = str(revision)
    return headers


async def _latest_state(client: httpx.AsyncClient, token: str) -> dict:
    response = await client.get("/api/export", headers=_headers(token))
    _expect_status(response, 200, "Song Bank smoke export")
    state = response.json()
    _require(isinstance(state.get("revision"), int), "export returned no data revision")
    _require(isinstance(state.get("songs"), list), "export returned no song array")
    return state


async def _cleanup_song_records(
    client: httpx.AsyncClient,
    token: str,
    *,
    song_ids: tuple[str, str],
    idea_id: str,
) -> None:
    """Remove only unique smoke records, reloading once on a revision conflict."""
    for song_id in song_ids:
        for attempt in (1, 2):
            state = await _latest_state(client, token)
            if not any(song.get("id") == song_id for song in state["songs"]):
                break
            response = await client.delete(
                f"/api/songs/{song_id}",
                headers=_headers(token, state["revision"]),
            )
            if response.status_code == 409 and attempt == 1:
                continue
            _expect_status(response, 200, f"cleanup song {song_id}")
            break

    for attempt in (1, 2):
        state = await _latest_state(client, token)
        if not any(idea.get("id") == idea_id for idea in state["ideas"]):
            return
        response = await client.delete(
            f"/api/ideas/{idea_id}",
            headers=_headers(token, state["revision"]),
        )
        if response.status_code == 409 and attempt == 1:
            continue
        _expect_status(response, 200, f"cleanup idea {idea_id}")
        return
    raise SmokeFailure("temporary Song Bank idea cleanup did not complete")


async def _exercise_song_bank(client: httpx.AsyncClient, token: str) -> None:
    """Exercise the isolated Song Bank lifecycle with uniquely named records."""
    suffix = secrets.token_hex(8)
    idea_id = f"deploy-smoke-idea-{suffix}"
    song_ids = (f"deploy-smoke-song-a-{suffix}", f"deploy-smoke-song-b-{suffix}")
    private_sentinel = f"private-song-smoke-{suffix}"

    try:
        state = await _latest_state(client, token)
        invalid = await client.put(
            "/api/data/songs",
            json=[
                *state["songs"],
                {
                    "id": f"deploy-smoke-invalid-{suffix}",
                    "artist": "Smoke Artist",
                    "title": "Invalid URL",
                    "youtubeUrl": "https://example.invalid/not-youtube",
                    "privateNotes": private_sentinel,
                    "status": "unused",
                    "assignedIdeaId": None,
                },
            ],
            headers=_headers(token, state["revision"]),
        )
        _expect_status(invalid, 422, "invalid Song Bank URL")
        unchanged = await _latest_state(client, token)
        _require(
            unchanged["revision"] == state["revision"],
            "rejected Song Bank write changed the data revision",
        )

        idea = {
            "id": idea_id,
            "titles": ["Deployment smoke idea"],
            "selectedTitle": "Deployment smoke idea",
            "summary": "Temporary non-production Song Bank validation",
            "outline": [],
            "status": "processed",
        }
        response = await client.put(
            "/api/data/ideas",
            json=[*state["ideas"], idea],
            headers=_headers(token, state["revision"]),
        )
        _expect_status(response, 200, "temporary Song Bank idea creation")
        state = response.json()["state"]

        songs = [
            {
                "id": song_ids[0],
                "artist": "Smoke Artist A",
                "title": "Smoke Song A",
                "youtubeUrl": "https://youtu.be/abcdefghijk",
                "privateNotes": private_sentinel,
                "status": "unused",
                "assignedIdeaId": None,
            },
            {
                "id": song_ids[1],
                "artist": "Smoke Artist B",
                "title": "Smoke Song B",
                "youtubeUrl": "https://www.youtube.com/watch?v=lmnopqrstuv",
                "privateNotes": private_sentinel,
                "status": "unused",
                "assignedIdeaId": None,
            },
        ]
        response = await client.put(
            "/api/data/songs",
            json=[*state["songs"], *songs],
            headers=_headers(token, state["revision"]),
        )
        _expect_status(response, 200, "temporary Song Bank creation")
        state = response.json()["state"]
        pre_assignment_revision = state["revision"]

        first = await client.put(
            f"/api/songs/{song_ids[0]}/assignment",
            json={"ideaId": idea_id},
            headers=_headers(token, state["revision"]),
        )
        _expect_status(first, 200, "first Song Bank assignment")
        state = first.json()["state"]

        stale = await client.put(
            f"/api/songs/{song_ids[1]}/assignment",
            json={"ideaId": idea_id},
            headers=_headers(token, pre_assignment_revision),
        )
        _expect_status(stale, 409, "stale Song Bank assignment")

        replacement = await client.put(
            f"/api/songs/{song_ids[1]}/assignment",
            json={"ideaId": idea_id},
            headers=_headers(token, state["revision"]),
        )
        _expect_status(replacement, 200, "replacement Song Bank assignment")
        state = replacement.json()["state"]
        by_id = {song["id"]: song for song in state["songs"]}
        _require(by_id[song_ids[0]]["status"] == "unused", "replaced song stayed used")
        _require(
            by_id[song_ids[1]]["assignedIdeaId"] == idea_id,
            "replacement song did not persist its idea",
        )

        reloaded = await _latest_state(client, token)
        by_id = {song["id"]: song for song in reloaded["songs"]}
        _require(
            by_id[song_ids[1]]["privateNotes"] == private_sentinel,
            "private Song Bank notes did not survive reload",
        )
        public_episodes = await client.get("/public/episodes")
        _expect_status(public_episodes, 200, "public episodes during Song Bank smoke")
        _require(
            private_sentinel not in public_episodes.text,
            "private Song Bank notes appeared in a public response",
        )

        retired = await client.put(
            f"/api/songs/{song_ids[1]}/status",
            json={"status": "retired"},
            headers=_headers(token, reloaded["revision"]),
        )
        _expect_status(retired, 200, "Song Bank retirement")
        state = retired.json()["state"]
        retired_song = next(song for song in state["songs"] if song["id"] == song_ids[1])
        _require(retired_song["status"] == "retired", "song did not retire")
        _require(retired_song["assignedIdeaId"] is None, "retired song stayed assigned")

        restored = await client.put(
            f"/api/songs/{song_ids[1]}/status",
            json={"status": "unused"},
            headers=_headers(token, state["revision"]),
        )
        _expect_status(restored, 200, "Song Bank restoration")
        state = restored.json()["state"]
        reassigned = await client.put(
            f"/api/songs/{song_ids[1]}/assignment",
            json={"ideaId": idea_id},
            headers=_headers(token, state["revision"]),
        )
        _expect_status(reassigned, 200, "restored Song Bank assignment")
        state = reassigned.json()["state"]

        deleted_idea = await client.delete(
            f"/api/ideas/{idea_id}",
            headers=_headers(token, state["revision"]),
        )
        _expect_status(deleted_idea, 200, "Song Bank idea deletion")
        state = deleted_idea.json()["state"]
        freed_song = next(song for song in state["songs"] if song["id"] == song_ids[1])
        _require(freed_song["status"] == "unused", "idea deletion did not free song")
        _require(freed_song["assignedIdeaId"] is None, "idea deletion left assignment")

        for song_id in song_ids:
            response = await client.delete(
                f"/api/songs/{song_id}",
                headers=_headers(token, state["revision"]),
            )
            _expect_status(response, 200, f"temporary Song Bank deletion {song_id}")
            state = response.json()["state"]
        _require(
            all(song.get("id") not in song_ids for song in state["songs"]),
            "temporary Song Bank records survived deletion",
        )
    finally:
        await _cleanup_song_records(
            client,
            token,
            song_ids=song_ids,
            idea_id=idea_id,
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

            for path in (
                "/",
                "/register.html",
                "/songs.html",
                "/js/show-song.js",
                "/js/songs.js",
                "/public/homepage",
            ):
                response = await client.get(path)
                _expect_status(response, 200, f"public route {path}")
                if path == "/songs.html":
                    _require(
                        "Song Bank" in response.text and "js/songs.js" in response.text,
                        "deployed Song Bank page is incomplete",
                    )
                elif path == "/js/songs.js":
                    _require(
                        "validateSongInput" in response.text,
                        "deployed Song Bank script is incomplete",
                    )
                elif path == "/js/show-song.js":
                    _require(
                        "renderPreparation" in response.text,
                        "deployed episode Song preparation script is incomplete",
                    )

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
            await _exercise_song_bank(client, token)

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
