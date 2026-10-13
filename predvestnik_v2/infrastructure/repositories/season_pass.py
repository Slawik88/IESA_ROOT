"""Storage of the free season pass: point receipts, daily caps, progress and claims."""
from __future__ import annotations

from datetime import date


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS season_pass_progress (
            user_id BIGINT NOT NULL,
            season INTEGER NOT NULL CHECK (season >= 1),
            points BIGINT NOT NULL DEFAULT 0 CHECK (points >= 0),
            claimed_level INTEGER NOT NULL DEFAULT 0 CHECK (claimed_level >= 0),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, season)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS season_pass_days (
            user_id BIGINT NOT NULL,
            season INTEGER NOT NULL CHECK (season >= 1),
            day DATE NOT NULL,
            points INTEGER NOT NULL DEFAULT 0 CHECK (points >= 0),
            PRIMARY KEY (user_id, season, day)
        )
    """)
    # One receipt per (player, source, game): a replayed event can never add points twice.
    await db.execute("""
        CREATE TABLE IF NOT EXISTS season_pass_receipts (
            user_id BIGINT NOT NULL,
            source TEXT NOT NULL,
            event_id TEXT NOT NULL,
            season INTEGER NOT NULL CHECK (season >= 1),
            day DATE NOT NULL,
            points INTEGER NOT NULL CHECK (points >= 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, source, event_id)
        )
    """)


async def lock_day(db, *, user_id: int, season: int, day: date) -> int:
    """Create the day row if needed, lock it, and return the points already earned that day."""
    await db.execute(
        "INSERT INTO season_pass_days(user_id,season,day,points) VALUES (?,?,?,0) ON CONFLICT DO NOTHING",
        (int(user_id), int(season), day),
    )
    async with db.execute(
        "SELECT points FROM season_pass_days WHERE user_id=? AND season=? AND day=? FOR UPDATE",
        (int(user_id), int(season), day),
    ) as cursor:
        return int((await cursor.fetchone())[0])


async def insert_receipt(db, *, user_id: int, source: str, event_id: str, season: int, day: date, points: int) -> bool:
    """False when this game was already counted."""
    async with db.execute(
        "INSERT INTO season_pass_receipts(user_id,source,event_id,season,day,points) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT DO NOTHING RETURNING 1",
        (int(user_id), source, event_id, int(season), day, int(points)),
    ) as cursor:
        return bool(await cursor.fetchone())


async def add_points(db, *, user_id: int, season: int, day: date, points: int) -> None:
    await db.execute(
        "UPDATE season_pass_days SET points=points+? WHERE user_id=? AND season=? AND day=?",
        (int(points), int(user_id), int(season), day),
    )
    await db.execute(
        "INSERT INTO season_pass_progress(user_id,season,points) VALUES (?,?,?) "
        "ON CONFLICT (user_id,season) DO UPDATE SET points=season_pass_progress.points+?, updated_at=NOW()",
        (int(user_id), int(season), int(points), int(points)),
    )


async def progress(db, *, user_id: int, season: int, lock: bool = False) -> dict | None:
    async with db.execute(
        "SELECT points,claimed_level FROM season_pass_progress WHERE user_id=? AND season=?"
        + (" FOR UPDATE" if lock else ""),
        (int(user_id), int(season)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def day_points(db, *, user_id: int, season: int, day: date) -> int:
    async with db.execute(
        "SELECT points FROM season_pass_days WHERE user_id=? AND season=? AND day=?",
        (int(user_id), int(season), day),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def set_claimed_level(db, *, user_id: int, season: int, level: int) -> None:
    await db.execute(
        "UPDATE season_pass_progress SET claimed_level=?, updated_at=NOW() WHERE user_id=? AND season=?",
        (int(level), int(user_id), int(season)),
    )
