"""Frozen results of finished game seasons, their payouts and closing markers.

``game_season_results`` + ``game_season_settlements`` are the frozen snapshot of
one board (a settlement row means "this board's places are frozen").  Money is
recorded separately in ``game_season_payouts`` (one row per player and season)
and the season is closed in ``game_season_closed`` once every payout is paid.
"""
from __future__ import annotations


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
    await db.execute("""
        CREATE TABLE IF NOT EXISTS game_season_payouts (
            season INTEGER NOT NULL CHECK (season >= 1),
            user_id BIGINT NOT NULL,
            game TEXT NOT NULL,
            board TEXT NOT NULL,
            place INTEGER NOT NULL CHECK (place >= 1),
            mora INTEGER NOT NULL CHECK (mora >= 0),
            essence INTEGER NOT NULL CHECK (essence >= 0),
            paid_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (season, user_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS game_season_closed (
            season INTEGER PRIMARY KEY CHECK (season >= 1),
            players INTEGER NOT NULL CHECK (players >= 0),
            mora_total BIGINT NOT NULL CHECK (mora_total >= 0),
            essence_total BIGINT NOT NULL CHECK (essence_total >= 0),
            closed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


async def try_lock_season(db, *, season: int) -> bool:
    """Session-scoped lock: one worker settles a season at a time.

    Payouts commit one player at a time, so the lock must outlive a single
    transaction; the caller releases it with ``unlock_season`` (a pooled
    connection also drops it on release).
    """
    async with db.execute("SELECT pg_try_advisory_lock(hashtextextended(?, 0))",
                          (f"season-settle:{int(season)}",)) as cursor:
        row = await cursor.fetchone()
    return bool(row[0])


async def unlock_season(db, *, season: int) -> None:
    async with db.execute("SELECT pg_advisory_unlock(hashtextextended(?, 0))",
                          (f"season-settle:{int(season)}",)) as cursor:
        await cursor.fetchone()


async def is_closed(db, *, season: int) -> bool:
    async with db.execute("SELECT 1 FROM game_season_closed WHERE season=?", (int(season),)) as cursor:
        return bool(await cursor.fetchone())


async def is_settled(db, *, game: str, board: str, season: int) -> bool:
    async with db.execute(
        "SELECT 1 FROM game_season_settlements WHERE game=? AND board=? AND season=?",
        (game, board, int(season)),
    ) as cursor:
        return bool(await cursor.fetchone())


async def insert_result(db, *, game: str, board: str, season: int, user_id: int, place: int,
                        result_json: str, reward_mora: int) -> None:
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


async def unpaid_batch(db, *, season: int, after_user_id: int, limit: int) -> list[dict]:
    """Next players with a reward and no payout yet: their best reward over all boards."""
    async with db.execute(
        "SELECT DISTINCT ON (r.user_id) r.user_id,r.game,r.board,r.place,r.reward_mora,"
        "COALESCE((r.result_json->>'reward_essence')::int,0) AS reward_essence "
        "FROM game_season_results r WHERE r.season=? AND r.user_id>? AND r.reward_mora>0 "
        "AND NOT EXISTS (SELECT 1 FROM game_season_payouts p WHERE p.season=r.season AND p.user_id=r.user_id) "
        "ORDER BY r.user_id,r.reward_mora DESC,reward_essence DESC,r.game,r.board LIMIT ?",
        (int(season), int(after_user_id), int(limit)),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def insert_payout(db, *, season: int, user_id: int, game: str, board: str, place: int,
                        mora: int, essence: int) -> bool:
    """Record the one payout of a player for a season; False when it already exists."""
    async with db.execute(
        "INSERT INTO game_season_payouts(season,user_id,game,board,place,mora,essence) "
        "VALUES (?,?,?,?,?,?,?) ON CONFLICT DO NOTHING RETURNING 1",
        (int(season), int(user_id), game, board, int(place), int(mora), int(essence)),
    ) as cursor:
        return bool(await cursor.fetchone())


async def unpaid_count(db, *, season: int) -> int:
    async with db.execute(
        "SELECT COUNT(DISTINCT r.user_id) FROM game_season_results r WHERE r.season=? AND r.reward_mora>0 "
        "AND NOT EXISTS (SELECT 1 FROM game_season_payouts p WHERE p.season=r.season AND p.user_id=r.user_id)",
        (int(season),),
    ) as cursor:
        return int((await cursor.fetchone())[0])


async def close_season(db, *, season: int) -> None:
    await db.execute(
        "INSERT INTO game_season_closed(season,players,mora_total,essence_total) "
        "SELECT ?,COUNT(*),COALESCE(SUM(mora),0),COALESCE(SUM(essence),0) FROM game_season_payouts WHERE season=? "
        "ON CONFLICT DO NOTHING",
        (int(season), int(season)),
    )
