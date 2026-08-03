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
from satt.models import (
    Guest,
    GuestAssignment,
    Idea,
    InviteCode,
    Top3Assignment,
    Top3Concept,
    User,
)

_ALLOWED_ENVIRONMENTS = {"development", "test"}
_PRODUCTION_HOSTS = {"saltallthethings.com", "www.saltallthethings.com"}
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}
_INVITE_CHARSET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


class SmokeFailure(RuntimeError):
    """A deployment smoke assertion failed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    """Inspect response structure without treating ordinary text as a leaked field."""
    if isinstance(value, dict):
        return any(
            key in forbidden or _contains_forbidden_key(item, forbidden)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


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
        await session.execute(delete(InviteCode).where(InviteCode.code == invite_code))
        await session.commit()


async def _cleanup_top3_records(idea_id: str, concept_ids: tuple[str, str]) -> None:
    """Remove only uniquely named Top 3 smoke records in dependency order."""
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            delete(Top3Assignment).where(Top3Assignment.idea_id == idea_id)
        )
        await session.execute(
            delete(Top3Concept).where(Top3Concept.id.in_(concept_ids))
        )
        await session.execute(delete(Idea).where(Idea.id == idea_id))
        await session.commit()


async def _cleanup_guest_records(
    guest_ids: tuple[str, ...], idea_ids: tuple[str, ...]
) -> None:
    """Remove only uniquely named Guest Bank smoke records."""
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            delete(GuestAssignment).where(GuestAssignment.guest_id.in_(guest_ids))
        )
        await session.execute(delete(Guest).where(Guest.id.in_(guest_ids)))
        await session.execute(delete(Idea).where(Idea.id.in_(idea_ids)))
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
    _require(isinstance(state.get("guests"), list), "export returned no guest array")
    _require(
        isinstance(state.get("guestAssignments"), list),
        "export returned no guest assignment array",
    )
    return state


async def _exercise_guest_bank(client: httpx.AsyncClient, token: str) -> None:
    """Exercise reusable guest links, lifecycle, privacy, and cleanup."""
    suffix = secrets.token_hex(8)
    guest_ids = (
        f"deploy-smoke-guest-a-{suffix}",
        f"deploy-smoke-guest-b-{suffix}",
    )
    idea_ids = (
        f"deploy-smoke-guest-idea-a-{suffix}",
        f"deploy-smoke-guest-idea-b-{suffix}",
        f"deploy-smoke-guest-idea-c-{suffix}",
    )
    private_sentinel = f"private-guest-smoke-{suffix}"
    try:
        state = await _latest_state(client, token)
        ideas = [
            {
                "id": idea_id,
                "titles": [f"Guest smoke {index}"],
                "selectedTitle": f"Guest smoke {index}",
                "summary": "Temporary isolated Guest Bank smoke record",
                "outline": [],
                "status": "processed",
            }
            for index, idea_id in enumerate(idea_ids, start=1)
        ]
        response = await client.put(
            "/api/data/ideas",
            json=[*state["ideas"], *ideas],
            headers=_headers(token, state["revision"]),
        )
        _expect_status(response, 200, "Guest Bank smoke ideas")
        state = response.json()["state"]
        guests = [
            {
                "id": guest_ids[0],
                "displayName": "Deployment Guest A",
                "privateNotes": private_sentinel,
                "status": "active",
            },
            {
                "id": guest_ids[1],
                "displayName": "Deployment Guest B",
                "privateNotes": "secondary private guest smoke record",
                "status": "active",
            },
        ]
        response = await client.put(
            "/api/data/guests",
            json=[*state["guests"], *guests],
            headers=_headers(token, state["revision"]),
        )
        _expect_status(response, 200, "Guest Bank smoke guests")
        state = response.json()["state"]

        for guest_id, idea_id in (
            (guest_ids[0], idea_ids[0]),
            (guest_ids[0], idea_ids[1]),
            (guest_ids[1], idea_ids[0]),
        ):
            response = await client.put(
                f"/api/guests/{guest_id}/assignments/{idea_id}",
                headers=_headers(token, state["revision"]),
            )
            _expect_status(response, 200, "Guest Bank smoke assignment")
            state = response.json()["state"]

        repeated_revision = state["revision"]
        repeated = await client.put(
            f"/api/guests/{guest_ids[0]}/assignments/{idea_ids[0]}",
            headers=_headers(token, repeated_revision),
        )
        _expect_status(repeated, 200, "idempotent Guest Bank assignment")
        _require(
            repeated.json()["revision"] == repeated_revision,
            "repeated Guest Bank assignment changed the data revision",
        )
        state = repeated.json()["state"]
        by_id = {guest["id"]: guest for guest in state["guests"]}
        _require(
            by_id[guest_ids[0]]["totalAppearances"] == 2,
            "reusable guest appearance count is incorrect",
        )
        _require(
            by_id[guest_ids[1]]["totalAppearances"] == 1,
            "multi-guest show appearance count is incorrect",
        )
        _require(
            by_id[guest_ids[0]]["firstAppearance"] is None
            and by_id[guest_ids[0]]["mostRecentAppearance"] is None,
            "unscheduled guest smoke appearances fabricated a date",
        )

        archived = await client.put(
            f"/api/guests/{guest_ids[0]}/status",
            json={"status": "archived"},
            headers=_headers(token, state["revision"]),
        )
        _expect_status(archived, 200, "archive Guest Bank smoke guest")
        archived_state = archived.json()["state"]
        rejected = await client.put(
            f"/api/guests/{guest_ids[0]}/assignments/{idea_ids[2]}",
            headers=_headers(token, archived_state["revision"]),
        )
        _expect_status(rejected, 409, "archived Guest Bank assignment rejection")

        for path in ("/public/episodes", "/public/homepage"):
            public_response = await client.get(path)
            _expect_status(public_response, 200, f"Guest Bank privacy route {path}")
            _require(
                private_sentinel not in public_response.text,
                "private Guest Bank notes appeared in a public response",
            )

        latest = await _latest_state(client, token)
        deleted = await client.delete(
            f"/api/ideas/{idea_ids[0]}",
            headers=_headers(token, latest["revision"]),
        )
        _expect_status(deleted, 200, "Guest Bank idea cascade")
        _require(
            all(
                assignment["ideaId"] != idea_ids[0]
                for assignment in deleted.json()["state"]["guestAssignments"]
            ),
            "idea deletion retained Guest Bank assignment links",
        )
    finally:
        await _cleanup_guest_records(guest_ids, idea_ids)


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
        retired_song = next(
            song for song in state["songs"] if song["id"] == song_ids[1]
        )
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


async def _exercise_top3(
    client: httpx.AsyncClient, owner_token: str, viewer_token: str
) -> None:
    """Exercise owner-only Top 3 picks and metadata-only cross-user reads."""
    suffix = secrets.token_hex(8)
    idea_id = f"deploy-smoke-top3-idea-{suffix}"
    concept_ids = (
        f"deploy-smoke-top3-concept-a-{suffix}",
        f"deploy-smoke-top3-concept-b-{suffix}",
    )
    private_pick = f"private-top3-pick-{suffix}"
    private_notes = f"private-top3-notes-{suffix}"
    submission_id = f"deploy-smoke-top3-submission-{suffix}"
    viewer_pick = f"viewer-private-top3-pick-{suffix}"
    viewer_submission_id = f"deploy-smoke-top3-viewer-submission-{suffix}"
    external_submission_id = f"deploy-smoke-top3-external-{suffix}"
    external_pick = f"shared-external-top3-pick-{suffix}"
    try:
        state = await _latest_state(client, owner_token)
        idea = {
            "id": idea_id,
            "titles": ["Deployment Top 3 smoke"],
            "selectedTitle": "Deployment Top 3 smoke",
            "summary": "Temporary non-production privacy validation",
            "outline": [],
            "status": "processed",
        }
        response = await client.put(
            "/api/data/ideas",
            json=[*state["ideas"], idea],
            headers=_headers(owner_token, state["revision"]),
        )
        _expect_status(response, 200, "temporary Top 3 idea creation")
        revision = response.json()["revision"]

        for concept_id in concept_ids:
            response = await client.post(
                "/api/top3/concepts",
                json={
                    "id": concept_id,
                    "name": "Deployment privacy list",
                    "description": "Temporary isolated Top 3 validation.",
                    "rules": "Exactly three distinct picks.",
                    "hostNotes": "Private deployment-only notes.",
                    "aiExample": ["Example One", "Example Two", "Example Three"],
                },
                headers=_headers(owner_token, revision),
            )
            _expect_status(response, 201, "temporary Top 3 concept creation")
            revision = response.json()["revision"]

        assigned = await client.put(
            f"/api/top3/episodes/{idea_id}/assignment",
            json={"conceptId": concept_ids[0]},
            headers=_headers(owner_token, revision),
        )
        _expect_status(assigned, 200, "Top 3 assignment")
        revision = assigned.json()["revision"]
        bank = await client.get("/api/top3/concepts", headers=_headers(owner_token))
        _expect_status(bank, 200, "Top 3 Bank assignment metadata")
        first_concept = next(
            item for item in bank.json()["concepts"] if item["id"] == concept_ids[0]
        )
        _require(
            first_concept["assignedEpisodes"]
            == [
                {
                    "ideaId": idea_id,
                    "title": "Deployment Top 3 smoke",
                    "episodeNumber": None,
                }
            ],
            "Top 3 Bank did not report assignment metadata",
        )
        _require(
            not _contains_forbidden_key(
                bank.json(), {"picks", "privateDiscussionNotes"}
            ),
            "Top 3 Bank exposed participant submission fields",
        )
        saved = await client.put(
            f"/api/top3/episodes/{idea_id}/submission",
            json={
                "id": submission_id,
                "picks": [private_pick, "Private Rank Two", "Private Rank Three"],
                "privateDiscussionNotes": private_notes,
            },
            headers=_headers(owner_token, revision),
        )
        _expect_status(saved, 200, "Top 3 owner submission")
        _require(private_pick in saved.text, "owner cannot reload their Top 3 picks")
        _require(private_notes in saved.text, "owner cannot reload their Top 3 notes")

        private_pick = f"updated-private-top3-pick-{suffix}"
        private_notes = f"updated-private-top3-notes-{suffix}"
        saved = await client.put(
            f"/api/top3/episodes/{idea_id}/submission",
            json={
                "id": submission_id,
                "picks": [private_pick, "Updated Rank Two", "Updated Rank Three"],
                "privateDiscussionNotes": private_notes,
            },
            headers=_headers(owner_token, saved.json()["revision"]),
        )
        _expect_status(saved, 200, "Top 3 owner submission update")
        _require(private_pick in saved.text, "owner edit did not persist")
        _require(private_notes in saved.text, "owner note edit did not persist")

        redacted = await client.get(
            f"/api/top3/episodes/{idea_id}", headers=_headers(viewer_token)
        )
        _expect_status(redacted, 200, "Top 3 redacted viewer read")
        _require(
            private_pick not in redacted.text, "another user received a private pick"
        )
        _require(
            private_notes not in redacted.text, "another user received private notes"
        )
        contributors = redacted.json()["assignment"]["contributors"]
        _require(
            any(item["complete"] and "picks" not in item for item in contributors),
            "redacted viewer received no metadata-only completed contributor",
        )

        viewer_saved = await client.put(
            f"/api/top3/episodes/{idea_id}/submission",
            json={
                "id": viewer_submission_id,
                "picks": [viewer_pick, "Viewer Rank Two", "Viewer Rank Three"],
                "privateDiscussionNotes": f"viewer-private-notes-{suffix}",
            },
            headers=_headers(viewer_token, redacted.json()["revision"]),
        )
        _expect_status(viewer_saved, 200, "Top 3 viewer submission")
        owner_before_reveal = await client.get(
            f"/api/top3/episodes/{idea_id}", headers=_headers(owner_token)
        )
        _expect_status(owner_before_reveal, 200, "Top 3 reverse-direction privacy")
        _require(
            viewer_pick not in owner_before_reveal.text,
            "owner received another user's unrevealed Top 3 pick",
        )

        revealed = await client.post(
            f"/api/top3/episodes/{idea_id}/reveals/{submission_id}",
            headers=_headers(viewer_token, viewer_saved.json()["revision"]),
        )
        _expect_status(revealed, 200, "Top 3 deliberate reveal")
        revealed_owner = next(
            item
            for item in revealed.json()["assignment"]["contributors"]
            if item["submissionId"] == submission_id
        )
        _require(
            revealed_owner.get("revealed") is True
            and revealed_owner.get("picks", [None])[0] == private_pick
            and revealed_owner.get("privateDiscussionNotes") == private_notes
            and bool(revealed_owner.get("revealedAt")),
            "viewer-specific reveal did not return picks, notes, and audit timestamp",
        )
        repeated_reveal = await client.post(
            f"/api/top3/episodes/{idea_id}/reveals/{submission_id}",
            headers=_headers(viewer_token, revealed.json()["revision"]),
        )
        _expect_status(repeated_reveal, 200, "Top 3 repeated reveal")
        repeated_owner = next(
            item
            for item in repeated_reveal.json()["assignment"]["contributors"]
            if item["submissionId"] == submission_id
        )
        _require(
            repeated_reveal.json()["revision"] == revealed.json()["revision"]
            and repeated_owner.get("revealedAt") == revealed_owner.get("revealedAt"),
            "repeated reveal changed revision or audit timestamp",
        )
        owner_after_reveal = await client.get(
            f"/api/top3/episodes/{idea_id}", headers=_headers(owner_token)
        )
        _expect_status(owner_after_reveal, 200, "Top 3 reveal direction isolation")
        _require(
            viewer_pick not in owner_after_reveal.text,
            "viewer-specific reveal leaked in the opposite direction",
        )

        external_created = await client.post(
            f"/api/top3/episodes/{idea_id}/external-submissions",
            json={
                "id": external_submission_id,
                "displayName": "Deployment Guest",
                "externalType": "guest",
                "picks": [external_pick, "Shared Rank Two", "Shared Rank Three"],
                "privateDiscussionNotes": f"shared-external-notes-{suffix}",
            },
            headers=_headers(owner_token, repeated_reveal.json()["revision"]),
        )
        _expect_status(external_created, 201, "shared external Top 3 creation")
        created_external = next(
            item
            for item in external_created.json()["assignment"]["contributors"]
            if item["submissionId"] == external_submission_id
        )
        entered_by_user_id = created_external.get("enteredByUserId")
        _require(
            external_pick in external_created.text and entered_by_user_id is not None,
            "external Top 3 result was not shared with audit attribution",
        )
        external_view = await client.get(
            f"/api/top3/episodes/{idea_id}", headers=_headers(viewer_token)
        )
        _expect_status(external_view, 200, "shared external Top 3 viewer read")
        _require(
            external_pick in external_view.text,
            "external Top 3 result was not shared across authenticated hosts",
        )
        external_edited = await client.put(
            f"/api/top3/episodes/{idea_id}/external-submissions/{external_submission_id}",
            json={
                "id": external_submission_id,
                "displayName": "Deployment Listener",
                "externalType": "listener",
                "picks": [external_pick, "Edited Rank Two", "Edited Rank Three"],
                "privateDiscussionNotes": f"edited-shared-notes-{suffix}",
            },
            headers=_headers(viewer_token, external_view.json()["revision"]),
        )
        _expect_status(external_edited, 200, "shared external Top 3 cross-user edit")
        edited_external = next(
            item
            for item in external_edited.json()["assignment"]["contributors"]
            if item["submissionId"] == external_submission_id
        )
        _require(
            edited_external.get("externalType") == "listener"
            and edited_external.get("enteredByUserId") == entered_by_user_id,
            "external Top 3 edit changed immutable entry attribution",
        )
        spotify_results = await client.post(
            f"/api/top3/episodes/{idea_id}/spotify-results",
            json={"purpose": "spotify-overview"},
            headers=_headers(owner_token),
        )
        _expect_status(spotify_results, 200, "Top 3 Spotify result composition")
        spotify_payload = spotify_results.json()
        top3_result = spotify_payload.get("top3") or {}
        _require(
            top3_result.get("listName") == "Deployment privacy list",
            "Top 3 Spotify result omitted the list name",
        )
        result_contributors = top3_result.get("contributors") or []
        _require(
            len(result_contributors) == 2
            and all(
                set(item) == {"displayName", "picks"} for item in result_contributors
            )
            and all(len(item["picks"]) == 3 for item in result_contributors),
            "Top 3 Spotify result was not the narrow exact-three contributor contract",
        )
        result_first_picks = [item["picks"][0] for item in result_contributors]
        _require(
            result_first_picks == [private_pick, external_pick]
            and result_contributors[0]["displayName"][:1].isupper(),
            "Top 3 Spotify result did not keep the viewer's proper-case account before external results",
        )
        spotify_text = spotify_results.text
        for expected_pick in (private_pick, external_pick):
            _require(
                expected_pick in spotify_text,
                "Top 3 Spotify result omitted a submitted contributor",
            )
        _require(
            viewer_pick not in spotify_text,
            "Top 3 Spotify result exposed another host before viewer reveal",
        )
        _require(
            private_notes not in spotify_text
            and f"viewer-private-notes-{suffix}" not in spotify_text
            and f"edited-shared-notes-{suffix}" not in spotify_text
            and not _contains_forbidden_key(
                spotify_payload,
                {
                    "privateDiscussionNotes",
                    "submissionId",
                    "externalType",
                    "enteredByUserId",
                    "revealedAt",
                    "accountUserId",
                },
            ),
            "Top 3 Spotify result exposed preparation or ownership metadata",
        )
        viewer_spotify = await client.post(
            f"/api/top3/episodes/{idea_id}/spotify-results",
            json={"purpose": "spotify-overview"},
            headers=_headers(viewer_token),
        )
        _expect_status(viewer_spotify, 200, "viewer Top 3 Spotify composition")
        viewer_first_picks = [
            item["picks"][0]
            for item in (viewer_spotify.json().get("top3") or {}).get(
                "contributors", []
            )
        ]
        _require(
            set(viewer_first_picks[:2]) == {private_pick, viewer_pick}
            and viewer_first_picks[2:] == [external_pick],
            "Top 3 Spotify result did not include the viewer's own and revealed account lists before external results",
        )
        repeated_spotify = await client.post(
            f"/api/top3/episodes/{idea_id}/spotify-results",
            json={"purpose": "spotify-overview"},
            headers=_headers(viewer_token),
        )
        _expect_status(repeated_spotify, 200, "repeated Top 3 Spotify composition")
        _require(
            repeated_spotify.json() == viewer_spotify.json(),
            "Top 3 Spotify result ordering or content was not deterministic",
        )
        preparation_after_spotify = await client.get(
            f"/api/top3/episodes/{idea_id}", headers=_headers(owner_token)
        )
        _expect_status(
            preparation_after_spotify,
            200,
            "Top 3 preparation privacy after Spotify composition",
        )
        _require(
            preparation_after_spotify.json()["revision"]
            == external_edited.json()["revision"],
            "Top 3 Spotify composition unexpectedly changed the data revision",
        )
        _require(
            viewer_pick not in preparation_after_spotify.text,
            "Spotify composition revealed a hidden list in preparation state",
        )
        external_spoof = await client.post(
            f"/api/top3/episodes/{idea_id}/external-submissions",
            json={
                "id": f"spoofed-external-{suffix}",
                "displayName": "Spoof",
                "externalType": "guest",
                "picks": ["One", "Two", "Three"],
                "accountUserId": 1,
            },
            headers=_headers(owner_token, external_edited.json()["revision"]),
        )
        _expect_status(external_spoof, 422, "external Top 3 account-owner spoof")
        external_deleted = await client.delete(
            f"/api/top3/episodes/{idea_id}/external-submissions/{external_submission_id}",
            headers=_headers(owner_token, external_edited.json()["revision"]),
        )
        _expect_status(external_deleted, 200, "shared external Top 3 cross-user delete")
        _require(
            external_pick not in external_deleted.text,
            "deleted external Top 3 result survived response reload",
        )

        spoof = await client.put(
            f"/api/top3/episodes/{idea_id}/submission",
            json={
                "id": "spoofed-owner",
                "picks": ["One", "Two", "Three"],
                "accountUserId": 1,
            },
            headers=_headers(viewer_token, external_deleted.json()["revision"]),
        )
        _expect_status(spoof, 422, "Top 3 owner spoof attempt")

        exported = await client.get("/api/export", headers=_headers(viewer_token))
        _expect_status(exported, 200, "Top 3 leakage export")
        _require(
            private_pick not in exported.text, "private Top 3 pick leaked to export"
        )
        _require(
            private_notes not in exported.text, "private Top 3 notes leaked to export"
        )
        _require(
            not any(key.lower().startswith("top3") for key in exported.json()),
            "general export unexpectedly contains Top 3 data",
        )

        replaced = await client.put(
            f"/api/top3/episodes/{idea_id}/assignment",
            json={"conceptId": concept_ids[1]},
            headers=_headers(owner_token, exported.json()["revision"]),
        )
        _expect_status(replaced, 200, "Top 3 assignment replacement")
        _require(
            private_pick not in replaced.text and private_notes not in replaced.text,
            "replacement retained picks from the prior concept",
        )
        revision = replaced.json()["revision"]

        bank = await client.get("/api/top3/concepts", headers=_headers(owner_token))
        _expect_status(bank, 200, "reloaded Top 3 Bank")
        first_concept = next(
            item for item in bank.json()["concepts"] if item["id"] == concept_ids[0]
        )
        first_payload = {
            key: first_concept.get(key)
            for key in (
                "id",
                "name",
                "description",
                "rules",
                "hostNotes",
                "aiExample",
                "status",
                "source",
                "aiProvider",
                "aiModelId",
                "aiGeneratedAt",
            )
        }
        first_payload["description"] = "Edited deployment Top 3 validation."
        first_payload["status"] = "retired"
        retired = await client.put(
            f"/api/top3/concepts/{concept_ids[0]}",
            json=first_payload,
            headers=_headers(owner_token, revision),
        )
        _expect_status(retired, 200, "Top 3 Bank edit and retirement")
        _require(
            retired.json()["concept"]["status"] == "retired"
            and retired.json()["concept"]["description"]
            == "Edited deployment Top 3 validation.",
            "Top 3 Bank edit or retirement did not persist",
        )

        first_payload["status"] = "active"
        restored = await client.put(
            f"/api/top3/concepts/{concept_ids[0]}",
            json=first_payload,
            headers=_headers(owner_token, retired.json()["revision"]),
        )
        _expect_status(restored, 200, "Top 3 Bank restoration")
        deleted = await client.delete(
            f"/api/top3/concepts/{concept_ids[0]}",
            headers=_headers(owner_token, restored.json()["revision"]),
        )
        _expect_status(deleted, 200, "Top 3 Bank deletion")
        reloaded = await client.get("/api/top3/concepts", headers=_headers(owner_token))
        _expect_status(reloaded, 200, "Top 3 Bank post-delete reload")
        _require(
            all(item["id"] != concept_ids[0] for item in reloaded.json()["concepts"]),
            "deleted Top 3 concept survived reload",
        )
        removed = await client.delete(
            f"/api/top3/episodes/{idea_id}/assignment",
            headers=_headers(owner_token, reloaded.json()["revision"]),
        )
        _expect_status(removed, 200, "Top 3 assignment removal")
        _require(
            removed.json()["assignment"] is None,
            "removed Top 3 assignment survived response reload",
        )
        removal_reload = await client.get(
            f"/api/top3/episodes/{idea_id}", headers=_headers(viewer_token)
        )
        _expect_status(removal_reload, 200, "Top 3 assignment removal reload")
        _require(
            removal_reload.json()["assignment"] is None,
            "removed Top 3 assignment survived viewer reload",
        )
    finally:
        await _cleanup_top3_records(idea_id, concept_ids)


async def _exercise_top3_ai_boundary(
    client: httpx.AsyncClient, token: str, exported_state: dict
) -> None:
    """Verify the deployed AI route without contacting an external provider."""
    config = exported_state.get("config") or {}
    _require("claudeApiKey" not in config, "Claude credential leaked to export")
    _require("openaiApiKey" not in config, "OpenAI credential leaked to export")
    _require(
        isinstance(config.get("claudeApiKeyConfigured"), bool),
        "Claude credential status is unavailable",
    )
    _require(
        isinstance(config.get("openaiApiKeyConfigured"), bool),
        "OpenAI credential status is unavailable",
    )

    unauthorized = await client.post(
        "/api/ai/top3-concept",
        json={"description": "Deployment-only route check"},
    )
    _expect_status(unauthorized, 401, "unauthenticated Top 3 AI generation")

    participant_shaped = await client.post(
        "/api/ai/top3-concept",
        json={
            "description": "Deployment-only route check",
            "participantPicks": ["One", "Two", "Three"],
        },
        headers=_headers(token),
    )
    _expect_status(participant_shaped, 422, "participant-shaped Top 3 AI input")

    provider = config.get("aiModel", "claude")
    configured_flag = f"{provider}ApiKeyConfigured"
    if provider in {"claude", "openai"} and config.get(configured_flag) is False:
        missing_credential = await client.post(
            "/api/ai/top3-concept",
            json={"description": "Deployment-only missing credential check"},
            headers=_headers(token),
        )
        _expect_status(missing_credential, 400, "Top 3 AI missing credential")
        _require(
            missing_credential.json().get("error")
            == f"No API key configured for {provider}",
            "Top 3 AI missing-credential response is not actionable",
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
    viewer_username = f"deploy-smoke-viewer-{secrets.token_hex(6)}"
    password = secrets.token_urlsafe(24)
    viewer_password = secrets.token_urlsafe(24)
    invite_code = "".join(secrets.choice(_INVITE_CHARSET) for _ in range(8))
    viewer_invite_code = "".join(secrets.choice(_INVITE_CHARSET) for _ in range(8))

    await _seed_invite(invite_code)
    await _seed_invite(viewer_invite_code)
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
                "/show_management.html",
                "/songs.html",
                "/guests.html",
                "/top3.html",
                "/js/show-song.js",
                "/js/episode-overview.js",
                "/js/songs.js",
                "/js/guests.js",
                "/js/top3-bank.js",
                "/js/top3-episode.js",
                "/public/homepage",
            ):
                response = await client.get(path)
                _expect_status(response, 200, f"public route {path}")
                if path == "/songs.html":
                    _require(
                        "Song Bank" in response.text and "js/songs.js" in response.text,
                        "deployed Song Bank page is incomplete",
                    )
                elif path == "/guests.html":
                    _require(
                        "Guest Bank" in response.text
                        and "js/guests.js" in response.text
                        and "Filter guests by status" in response.text,
                        "deployed Guest Bank page is incomplete",
                    )
                elif path == "/show_management.html":
                    _require(
                        "js/top3-episode.js" in response.text
                        and "Top3EpisodePlanning.render" in response.text
                        and "Top3EpisodePlanning.summaryMarkup" in response.text,
                        "deployed Show Management Top 3 controls are incomplete",
                    )
                elif path == "/top3.html":
                    _require(
                        "Top 3 Bank" in response.text
                        and "js/top3-bank.js" in response.text
                        and "Fictional examples" in response.text,
                        "deployed Top 3 Bank page is incomplete",
                    )
                elif path == "/js/top3-bank.js":
                    _require(
                        "conceptCardMarkup" in response.text
                        and "/ai/top3-concept" in response.text
                        and "If-Match" in response.text,
                        "deployed Top 3 Bank script is incomplete",
                    )
                elif path == "/js/top3-episode.js":
                    _require(
                        "Top3EpisodePlanning" in response.text
                        and "Top 3 preparation" in response.text
                        and "/assignment" in response.text
                        and "/submission" in response.text
                        and "If-Match" in response.text,
                        "deployed Top 3 episode-planning script is incomplete",
                    )
                elif path == "/js/songs.js":
                    _require(
                        "validateSongInput" in response.text,
                        "deployed Song Bank script is incomplete",
                    )
                elif path == "/js/guests.js":
                    _require(
                        "guestCardMarkup" in response.text
                        and "validateGuestInput" in response.text
                        and "appearanceHistory" in response.text,
                        "deployed Guest Bank script is incomplete",
                    )
                elif path == "/js/show-song.js":
                    _require(
                        "renderPreparation" in response.text,
                        "deployed episode Song preparation script is incomplete",
                    )
                elif path == "/js/episode-overview.js":
                    _require(
                        "publicSongBlock" in response.text
                        and "publicTop3Block" in response.text
                        and "clipboard.writeText" in response.text,
                        "deployed Spotify overview script is incomplete",
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

            viewer_registration = await client.post(
                "/api/auth/register",
                json={
                    "username": viewer_username,
                    "password": viewer_password,
                    "inviteCode": viewer_invite_code,
                },
            )
            _expect_status(viewer_registration, 201, "viewer registration")
            viewer_token = viewer_registration.json().get("token")
            _require(
                isinstance(viewer_token, str) and viewer_token,
                "viewer registration returned no token",
            )

            authenticated_export = await client.get(
                "/api/export",
                headers={"Authorization": f"Bearer {token}"},
            )
            _expect_status(authenticated_export, 200, "authenticated export")
            await _exercise_top3_ai_boundary(client, token, authenticated_export.json())
            await _exercise_song_bank(client, token)
            await _exercise_guest_bank(client, token)
            await _exercise_top3(client, token, viewer_token)

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
        await _cleanup_identity(viewer_username, viewer_invite_code)
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
