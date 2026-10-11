"""Settled results of finished game seasons (history + one-time rewards)."""
from __future__ import annotations

from infrastructure.repositories import public_profiles_v1 as public_profiles


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS game_season_results (
            game TEXT NOT NULL,
            board TEXT NOT NULL,
            season INTEGER NOT NULL CHECK (season >= 1),
            user_id BIGINT NOT NULL,
            place INTEGER NOT NULL CHECK (place >= 1),
            result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            reward_mora INTEGER NOT NULL DEFAULT 0 CHECK (reward_mora >= 0),
            settled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (game, board, season, user_id)
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS game_season_results_user
        ON game_season_results(user_id, settled_at DESC)
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS game_season_settlements (
            game TEXT NOT NULL,
            board TEXT NOT NULL,
            season INTEGER NOT NULL CHECK (season >= 1),
            players INTEGER NOT NULL DEFAULT 0,
            settled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (game, board, season)
        )
    """)


async def try_lock_board(db, *, game: str, board: str) -> bool:
    """Transaction-scoped lock: concurrent leaderboard views settle only once."""
    async with db.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(?, 0))",
                          (f"season:{game}:{board}",)) as cursor:
        row = await cursor.fetchone()
    return bool(row[0])


async def is_settled(db, *, game: str, board: str, season: int) -> bool:
    async with db.execute(
        "SELECT 1 FROM game_season_settlements WHERE game=? AND board=? AND season=?",
        (game, board, int(season)),
    ) as cursor:
        return bool(await cursor.fetchone())


async def insert_result(db, *, game: str, board: str, season: int, user_id: int, place: int,
                        result_json: str, reward_mora: int) -> None:
    await public_profiles.ensure_reference(db, user_id=int(user_id))
    await db.execute(
        "INSERT INTO game_season_results(game,board,season,user_id,place,result_json,reward_mora) "
        "VALUES (?,?,?,?,?,?::jsonb,?) ON CONFLICT DO NOTHING",
        (game, board, int(season), int(user_id), int(place), result_json, int(reward_mora)),
    )


async def mark_settled(db, *, game: str, board: str, season: int, players: int) -> None:
    await db.execute(
        "INSERT INTO game_season_settlements(game,board,season,players) VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
        (game, board, int(season), int(players)),
    )


async def last_result(db, *, game: str, board: str, user_id: int) -> dict | None:
    """The player's result in the most recently settled season of one board."""
    async with db.execute(
        "SELECT season,place,result_json,reward_mora FROM game_season_results "
        "WHERE game=? AND board=? AND user_id=? ORDER BY season DESC LIMIT 1",
        (game, board, int(user_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def history(db, *, game: str, board: str, user_id: int) -> list[dict]:
    async with db.execute(
        "SELECT season,place,result_json,reward_mora FROM game_season_results "
        "WHERE game=? AND board=? AND user_id=? ORDER BY season DESC LIMIT 20",
        (game, board, int(user_id)),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]
