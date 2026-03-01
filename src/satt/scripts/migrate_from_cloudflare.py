"""One-time migration script: Cloudflare KV → Postgres.

Usage:
    python src/satt/scripts/migrate_from_cloudflare.py \\
        --api-url https://saltallthethings.com \\
        --password <admin_password>

    # Dry run (no DB writes):
    python src/satt/scripts/migrate_from_cloudflare.py --dry-run

Safe to run multiple times — all inserts are upserts.
Do NOT delete from Cloudflare until Phase 4 cutover.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure src/ is on path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import httpx
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")


def _parse_dt(value: str | None) -> datetime | None:
    """Parse ISO 8601 string → datetime. asyncpg requires datetime objects."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_date(value: str | None):
    """Parse YYYY-MM-DD string → date. asyncpg requires date objects."""
    if not value:
        return None
    from datetime import date
    return date.fromisoformat(value)


# ---------------------------------------------------------------------------
# Fetch from Cloudflare
# ---------------------------------------------------------------------------


def fetch_from_cloudflare(api_url: str, password: str) -> dict:
    """GET /export from the Cloudflare Worker with X-Auth header."""
    url = api_url.rstrip("/") + "/export"
    print(f"Fetching {url} ...")
    with httpx.Client(timeout=30) as client:
        resp = client.get(url, headers={"X-Auth": password})
        resp.raise_for_status()
    data = resp.json()
    print(f"  Received keys: {list(data.keys())}")
    return data


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------


async def migrate_config(session: AsyncSession, config: dict, dry_run: bool) -> None:
    if dry_run:
        print(f"  [dry-run] Would upsert config")
        return
    await session.execute(
        text("""
            INSERT INTO satt.config (id, data, updated_at)
            VALUES (1, :data, now())
            ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()
        """),
        {"data": json.dumps(config)},
    )


async def migrate_ideas(session: AsyncSession, ideas: list, dry_run: bool) -> int:
    if not ideas:
        return 0
    if dry_run:
        print(f"  [dry-run] Would upsert {len(ideas)} ideas")
        return len(ideas)
    count = 0
    for idea in ideas:
        await session.execute(
            text("""
                INSERT INTO satt.ideas (
                    id, titles, selected_title, summary, outline,
                    status, image_file_id, raw_notes, created_at, updated_at
                )
                VALUES (
                    :id, :titles, :selected_title, :summary, :outline,
                    :status, :image_file_id, :raw_notes,
                    COALESCE(:created_at, now()), COALESCE(:updated_at, now())
                )
                ON CONFLICT (id) DO UPDATE SET
                    titles = EXCLUDED.titles,
                    selected_title = EXCLUDED.selected_title,
                    summary = EXCLUDED.summary,
                    outline = EXCLUDED.outline,
                    status = EXCLUDED.status,
                    image_file_id = EXCLUDED.image_file_id,
                    raw_notes = EXCLUDED.raw_notes,
                    updated_at = EXCLUDED.updated_at
            """),
            {
                "id": idea["id"],
                "titles": json.dumps(idea.get("titles", [])),
                "selected_title": idea.get("selectedTitle"),
                "summary": idea.get("summary"),
                "outline": json.dumps(idea.get("outline", [])),
                "status": idea.get("status", "draft"),
                "image_file_id": idea.get("imageFileId"),
                "raw_notes": idea.get("rawNotes"),
                "created_at": _parse_dt(idea.get("createdAt")),
                "updated_at": _parse_dt(idea.get("updatedAt")),
            },
        )
        count += 1
    return count


async def migrate_jokes(session: AsyncSession, jokes: list, dry_run: bool) -> int:
    if not jokes:
        return 0
    if dry_run:
        print(f"  [dry-run] Would upsert {len(jokes)} jokes")
        return len(jokes)
    count = 0
    for joke in jokes:
        await session.execute(
            text("""
                INSERT INTO satt.jokes (id, text, status, source, used_by_idea_id, created_at)
                VALUES (:id, :text, :status, :source, :used_by_idea_id, COALESCE(:created_at, now()))
                ON CONFLICT (id) DO UPDATE SET
                    text = EXCLUDED.text,
                    status = EXCLUDED.status,
                    source = EXCLUDED.source,
                    used_by_idea_id = EXCLUDED.used_by_idea_id
            """),
            {
                "id": joke["id"],
                "text": joke["text"],
                "status": joke.get("status", "active"),
                "source": joke.get("source", "manual"),
                "used_by_idea_id": joke.get("usedByIdeaId"),
                "created_at": _parse_dt(joke.get("createdAt")),
            },
        )
        count += 1
    return count


async def migrate_show_slots(session: AsyncSession, slots: list, dry_run: bool) -> int:
    if not slots:
        return 0
    if dry_run:
        print(f"  [dry-run] Would upsert {len(slots)} show slots")
        return len(slots)
    count = 0
    for slot in slots:
        await session.execute(
            text("""
                INSERT INTO satt.show_slots (
                    id, episode_number, episode_num, record_date, release_date,
                    is_rollout, release_date_override
                )
                VALUES (
                    :id, :episode_number, :episode_num, :record_date, :release_date,
                    :is_rollout, :release_date_override
                )
                ON CONFLICT (id) DO UPDATE SET
                    episode_number = EXCLUDED.episode_number,
                    episode_num = EXCLUDED.episode_num,
                    record_date = EXCLUDED.record_date,
                    release_date = EXCLUDED.release_date,
                    is_rollout = EXCLUDED.is_rollout,
                    release_date_override = EXCLUDED.release_date_override
            """),
            {
                "id": slot["id"],
                "episode_number": slot.get("episodeNumber", ""),
                "episode_num": slot.get("episodeNum", 0),
                "record_date": _parse_date(slot.get("recordDate")),
                "release_date": _parse_date(slot.get("releaseDate")),
                "is_rollout": slot.get("isRollout", False),
                "release_date_override": _parse_date(slot.get("releaseDateOverride")),
            },
        )
        count += 1
    return count


async def migrate_assignments(session: AsyncSession, assignments: dict, dry_run: bool) -> int:
    if not assignments:
        return 0
    if dry_run:
        print(f"  [dry-run] Would upsert {len(assignments)} assignments")
        return len(assignments)
    count = 0
    for slot_id, idea_id in assignments.items():
        await session.execute(
            text("""
                INSERT INTO satt.assignments (slot_id, idea_id)
                VALUES (:slot_id, :idea_id)
                ON CONFLICT (slot_id) DO UPDATE SET idea_id = EXCLUDED.idea_id
            """),
            {"slot_id": slot_id, "idea_id": idea_id},
        )
        count += 1
    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run_migration(data: dict, database_url: str, dry_run: bool) -> None:
    if dry_run:
        # No DB connection needed
        engine = None
        session = None
    else:
        engine = create_async_engine(database_url, echo=False)
        factory = async_sessionmaker(engine, expire_on_commit=False)

    if dry_run:
        print("\nMigrating config...")
        await migrate_config(None, data.get("config", {}), dry_run)
        print("Migrating ideas...")
        n_ideas = await migrate_ideas(None, data.get("ideas", []), dry_run)
        print("Migrating jokes...")
        n_jokes = await migrate_jokes(None, data.get("jokes", []), dry_run)
        print("Migrating show slots...")
        n_slots = await migrate_show_slots(None, data.get("showSlots", []), dry_run)
        print("Migrating assignments...")
        n_assignments = await migrate_assignments(None, data.get("assignments", {}), dry_run)
        print(f"\n[DRY RUN] Migration complete:")
        print(f"  {n_ideas} ideas")
        print(f"  {n_jokes} jokes")
        print(f"  {n_slots} show slots")
        print(f"  {n_assignments} assignments")
        print(f"  config: 1 row")
        return

    async with factory() as session:
        try:
            print("\nMigrating config...")
            await migrate_config(session, data.get("config", {}), dry_run)

            print("Migrating ideas...")
            n_ideas = await migrate_ideas(session, data.get("ideas", []), dry_run)

            print("Migrating jokes...")
            n_jokes = await migrate_jokes(session, data.get("jokes", []), dry_run)

            print("Migrating show slots...")
            n_slots = await migrate_show_slots(session, data.get("showSlots", []), dry_run)

            print("Migrating assignments...")
            n_assignments = await migrate_assignments(
                session, data.get("assignments", {}), dry_run
            )

            if not dry_run:
                await session.commit()

            print(f"\n{'[DRY RUN] ' if dry_run else ''}Migration complete:")
            print(f"  {n_ideas} ideas")
            print(f"  {n_jokes} jokes")
            print(f"  {n_slots} show slots")
            print(f"  {n_assignments} assignments")
            print(f"  config: 1 row")

        except Exception:
            await session.rollback()
            raise
    await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Migrate SATT data from Cloudflare KV to Postgres")
    parser.add_argument("--api-url", help="Cloudflare Worker URL (e.g. https://saltallthethings.com)")
    parser.add_argument("--password", help="Admin password for X-Auth header")
    parser.add_argument("--input-file", help="Load from local JSON export file instead of fetching")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate but do not write to DB")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url and not args.dry_run:
        print("ERROR: DATABASE_URL not set. Add it to .env or export it.")
        sys.exit(1)

    # Fetch data
    if args.input_file:
        print(f"Loading from {args.input_file} ...")
        with open(args.input_file) as f:
            data = json.load(f)
    elif args.api_url and args.password:
        data = fetch_from_cloudflare(args.api_url, args.password)
    elif args.dry_run:
        print("Dry run with empty dataset (no --api-url or --input-file provided)")
        data = {"config": {}, "ideas": [], "jokes": [], "showSlots": [], "assignments": {}}
    else:
        parser.error("Provide --api-url + --password, or --input-file, or --dry-run")

    asyncio.run(run_migration(data, database_url, args.dry_run))


if __name__ == "__main__":
    main()
