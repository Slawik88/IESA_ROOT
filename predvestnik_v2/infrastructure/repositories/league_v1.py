"""Storage of the League demo: level attempts (runs) and the best stars per level and season.

The board of a Minesweeper run (``board_json``) is server-only and never sent to a player.
"""
from __future__ import annotations

import json


def dumps(value) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def load(value):
    return json.loads(value) if isinstance(value, str) else value


async def ensure_tables(db) -> None:
    # No DDL on installed /me and pet-action paths; recheck after the schema lock.
    if await _schema_ready(db):
        return
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(hashtextextended('ensure_tables:league_demo', 0))")
        if not await _schema_ready(db):
            await _ensure_tables_unlocked(db)


async def _schema_ready(db) -> bool:
    async with db.execute("""
        SELECT NOT EXISTS (
            SELECT 1 FROM unnest(ARRAY[
                'league_demo_runs', 'league_demo_one_active_run',
                'league_demo_progress', 'league_demo_pet_xp_events'
            ]) AS name WHERE to_regclass(name) IS NULL
        )
    """) as cursor:
        return bool((await cursor.fetchone())[0])


async def _ensure_tables_unlocked(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS league_demo_runs (
            run_id TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            season TEXT NOT NULL,
            game TEXT NOT NULL CHECK (game IN ('minesweeper','rhythm')),
            level INTEGER NOT NULL CHECK (level >= 1),
            seed BYTEA NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active','won','lost','finished','cancelled')),
            board_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            revision INTEGER NOT NULL DEFAULT 0,
            started_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(),
            finished_at TIMESTAMPTZ NULL
        )
    """)
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS league_demo_one_active_run
        ON league_demo_runs(user_id, game) WHERE status = 'active'
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS league_demo_progress (
            user_id BIGINT NOT NULL,
            season TEXT NOT NULL,
            game TEXT NOT NULL,
            level INTEGER NOT NULL,
            stars SMALLINT NOT NULL DEFAULT 0 CHECK (stars BETWEEN 0 AND 3),
            attempts INTEGER NOT NULL DEFAULT 0,
            xp INTEGER NOT NULL DEFAULT 0,
            best_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            first_cleared_at TIMESTAMPTZ NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, season, game, level)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS league_demo_pet_xp_events (
            user_id BIGINT NOT NULL,
            season TEXT NOT NULL,
            source TEXT NOT NULL,
            event_id TEXT NOT NULL,
            xp INTEGER NOT NULL CHECK (xp > 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, season, source, event_id)
        )
    """)


async def add_pet_xp(db, *, user_id: int, season: str, source: str, event_id: str, xp: int) -> None:
    await db.execute(
        "INSERT INTO league_demo_pet_xp_events(user_id,season,source,event_id,xp) VALUES (?,?,?,?,?) "
        "ON CONFLICT (user_id,season,source,event_id) DO NOTHING",
        (int(user_id), season, source, str(event_id), int(xp)),
    )


async def pet_xp(db, *, user_id: int, season: str) -> int:
    async with db.execute(
        "SELECT COALESCE(SUM(xp),0) FROM league_demo_pet_xp_events WHERE user_id=? AND season=?",
        (int(user_id), season),
    ) as cursor:
        return int((await cursor.fetchone())[0])


async def lock_user(db, *, user_id: int) -> None:
    await db.execute("SELECT pg_advisory_xact_lock(hashtextextended(?, 0))", (f"league-demo:{int(user_id)}",))


async def progress(db, *, user_id: int, season: str) -> list[dict]:
    async with db.execute(
        "SELECT game, level, stars, attempts, xp, best_json FROM league_demo_progress "
        "WHERE user_id=? AND season=? ORDER BY game, level", (int(user_id), season),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def level_row(db, *, user_id: int, season: str, game: str, level: int) -> dict | None:
    async with db.execute(
        "SELECT stars, attempts, xp, best_json FROM league_demo_progress WHERE user_id=? AND season=? AND game=? AND level=? FOR UPDATE",
        (int(user_id), season, game, int(level)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def save_level(db, *, user_id: int, season: str, game: str, level: int, stars: int, xp: int, best: dict | None) -> None:
    """Count one finished attempt; stars and experience only ever go up."""
    await db.execute(
        "INSERT INTO league_demo_progress(user_id,season,game,level,stars,attempts,xp,best_json,first_cleared_at) "
        "VALUES (?,?,?,?,?,1,?,?::jsonb,CASE WHEN ?>0 THEN NOW() END) "
        "ON CONFLICT (user_id,season,game,level) DO UPDATE SET attempts=league_demo_progress.attempts+1,"
        "stars=GREATEST(league_demo_progress.stars,EXCLUDED.stars),xp=league_demo_progress.xp+EXCLUDED.xp,"
        "best_json=CASE WHEN EXCLUDED.stars>league_demo_progress.stars THEN EXCLUDED.best_json ELSE league_demo_progress.best_json END,"
        "first_cleared_at=COALESCE(league_demo_progress.first_cleared_at,EXCLUDED.first_cleared_at),updated_at=NOW()",
        (int(user_id), season, game, int(level), int(stars), int(xp), dumps(best or {}), int(stars)),
    )


async def insert_run(db, *, run_id: str, user_id: int, season: str, game: str, level: int, seed: bytes,
                     board: dict, state: dict) -> None:
    await db.execute(
        "INSERT INTO league_demo_runs(run_id,user_id,season,game,level,seed,status,board_json,state_json) "
        "VALUES (?,?,?,?,?,?,'active',?::jsonb,?::jsonb)",
        (run_id, int(user_id), season, game, int(level), seed, dumps(board), dumps(state)),
    )


async def active_run(db, *, user_id: int, game: str) -> dict | None:
    async with db.execute(
        "SELECT *, CLOCK_TIMESTAMP() AS server_now FROM league_demo_runs WHERE user_id=? AND game=? AND status='active' FOR UPDATE",
        (int(user_id), game),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def lock_run(db, *, run_id: str, user_id: int) -> dict | None:
    async with db.execute(
        "SELECT *, CLOCK_TIMESTAMP() AS server_now FROM league_demo_runs WHERE run_id=? AND user_id=? FOR UPDATE",
        (str(run_id), int(user_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def update_run(db, *, run_id: str, status: str, state: dict, revision: int, result: dict | None = None,
                     finished: bool = False) -> None:
    await db.execute(
        "UPDATE league_demo_runs SET status=?,state_json=?::jsonb,revision=?,result_json=COALESCE(?::jsonb,result_json),"
        "finished_at=CASE WHEN ? THEN CLOCK_TIMESTAMP() ELSE finished_at END WHERE run_id=?",
        (status, dumps(state), int(revision), dumps(result) if result is not None else None, bool(finished), str(run_id)),
    )


async def top(db, *, season: str, game: str, limit: int = 10) -> list[dict]:
    """Season standings of the demo: highest cleared level, then stars, then who got there first."""
    async with db.execute(
        "SELECT user_id, MAX(level) FILTER (WHERE stars>0) AS best_level, SUM(stars) AS stars, "
        "MAX(first_cleared_at) FILTER (WHERE stars>0) AS reached_at FROM league_demo_progress "
        "WHERE season=? AND game=? GROUP BY user_id HAVING MAX(level) FILTER (WHERE stars>0) IS NOT NULL "
        "ORDER BY best_level DESC, stars DESC, reached_at ASC, user_id ASC LIMIT ?",
        (season, game, int(limit)),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def reset(db, *, user_id: int, season: str) -> None:
    """Demo only: forget the caller's own progress and runs of this season."""
    await db.execute("DELETE FROM league_demo_pet_xp_events WHERE user_id=? AND season=?", (int(user_id), season))
    await db.execute("DELETE FROM league_demo_progress WHERE user_id=? AND season=?", (int(user_id), season))
    await db.execute("DELETE FROM league_demo_runs WHERE user_id=? AND season=?", (int(user_id), season))
