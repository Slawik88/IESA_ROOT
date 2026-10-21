"""PostgreSQL persistence for server-owned Minesweeper games."""
from __future__ import annotations

import json

from core import minesweeper_v2 as rules
from infrastructure.repositories import public_profiles_v1 as public_profiles


def dumps(value) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def load(value):
    return json.loads(value) if isinstance(value, str) else value


async def ensure_tables(db) -> None:
    await public_profiles.ensure_tables(db)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS minesweeper_v2_runs (
            run_id TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            difficulty TEXT NOT NULL CHECK (difficulty IN ('easy','normal','hard')),
            ruleset_version TEXT NOT NULL,
            seed BYTEA NOT NULL,
            first_cell INTEGER NULL,
            revealed_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            flags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            status TEXT NOT NULL CHECK (status IN ('awaiting_first_open','active','won','lost','cancelled')),
            revision INTEGER NOT NULL DEFAULT 0,
            opened_actions INTEGER NOT NULL DEFAULT 0,
            started_at TIMESTAMPTZ NULL,
            finished_at TIMESTAMPTZ NULL,
            elapsed_ms BIGINT NULL CHECK (elapsed_ms IS NULL OR elapsed_ms >= 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS minesweeper_v2_one_open_run_per_user
        ON minesweeper_v2_runs(user_id) WHERE status IN ('awaiting_first_open','active')
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS minesweeper_v2_actions (
            run_id TEXT NOT NULL REFERENCES minesweeper_v2_runs(run_id),
            action_id TEXT NOT NULL,
            request_json JSONB NOT NULL,
            result_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(run_id, action_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS minesweeper_v2_leaderboard (
            user_id BIGINT NOT NULL,
            difficulty TEXT NOT NULL CHECK (difficulty IN ('easy','normal','hard')),
            ruleset_version TEXT NOT NULL,
            best_elapsed_ms BIGINT NOT NULL CHECK (best_elapsed_ms >= 0),
            best_opened_actions INTEGER NOT NULL CHECK (best_opened_actions >= 1),
            best_run_id TEXT NOT NULL REFERENCES minesweeper_v2_runs(run_id),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id,difficulty,ruleset_version)
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS minesweeper_v2_leaderboard_rank
        ON minesweeper_v2_leaderboard(difficulty,ruleset_version,best_elapsed_ms,best_opened_actions,updated_at)
    """)


async def lock_owned_run(db, *, run_id: str, user_id: int) -> dict | None:
    async with db.execute("SELECT *, CLOCK_TIMESTAMP() AS server_now FROM minesweeper_v2_runs WHERE run_id=? AND user_id=? FOR UPDATE", (str(run_id), int(user_id))) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def action(db, *, run_id: str, action_id: str) -> dict | None:
    async with db.execute("SELECT request_json,result_json FROM minesweeper_v2_actions WHERE run_id=? AND action_id=?", (str(run_id), str(action_id))) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def save_action(db, *, run_id: str, action_id: str, request: dict, result: dict) -> None:
    await db.execute("INSERT INTO minesweeper_v2_actions(run_id,action_id,request_json,result_json) VALUES (?,?,?::jsonb,?::jsonb)", (str(run_id), str(action_id), dumps(request), dumps(result)))


async def update_run(db, *, run_id: str, first_cell: int | None, revealed: set[int], flags: set[int],
                     status: str, revision: int, opened_actions: int, started_at, finished_at, elapsed_ms: int | None) -> None:
    await db.execute(
        "UPDATE minesweeper_v2_runs SET first_cell=?,revealed_json=?::jsonb,flags_json=?::jsonb,status=?,revision=?,opened_actions=?,"
        "started_at=(?::timestamp AT TIME ZONE 'UTC'),finished_at=(?::timestamp AT TIME ZONE 'UTC'),elapsed_ms=? WHERE run_id=?",
        (first_cell, dumps(sorted(revealed)), dumps(sorted(flags)), status, int(revision), int(opened_actions), started_at, finished_at, elapsed_ms, str(run_id)),
    )


async def upsert_leaderboard(db, *, run_id: str, user_id: int, difficulty: str,
                             ruleset_version: str, elapsed_ms: int, opened_actions: int) -> None:
    if not rules.speed_ranked(status="won", opened_actions=opened_actions, elapsed_ms=elapsed_ms):
        return
    await public_profiles.ensure_reference(db, user_id=int(user_id))
    await db.execute(
        "INSERT INTO minesweeper_v2_leaderboard(user_id,difficulty,ruleset_version,best_elapsed_ms,best_opened_actions,best_run_id) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(user_id,difficulty,ruleset_version) DO UPDATE SET best_elapsed_ms=EXCLUDED.best_elapsed_ms,best_opened_actions=EXCLUDED.best_opened_actions,best_run_id=EXCLUDED.best_run_id,updated_at=NOW() "
        "WHERE (EXCLUDED.best_elapsed_ms,EXCLUDED.best_opened_actions) < (minesweeper_v2_leaderboard.best_elapsed_ms,minesweeper_v2_leaderboard.best_opened_actions)",
        (int(user_id), str(difficulty), str(ruleset_version), int(elapsed_ms), int(opened_actions), str(run_id)),
    )


_SEASON_BEST = (
    "WITH best AS (SELECT DISTINCT ON (user_id) user_id,elapsed_ms AS best_elapsed_ms,opened_actions AS best_opened_actions,finished_at "
    "FROM minesweeper_v2_runs WHERE difficulty=? AND status='won' AND elapsed_ms>0 AND opened_actions>=2 "
    "AND finished_at>=(?::timestamp AT TIME ZONE 'UTC') AND finished_at<(?::timestamp AT TIME ZONE 'UTC') "
    "ORDER BY user_id,elapsed_ms ASC,opened_actions ASC,finished_at ASC,run_id ASC), "
    "ranked AS (SELECT user_id,best_elapsed_ms,best_opened_actions,"
    "RANK() OVER (ORDER BY best_elapsed_ms ASC,best_opened_actions ASC,finished_at ASC) AS place FROM best) "
)


async def season_standings(db, *, difficulty: str, starts_at, ends_at, limit: int | None = None) -> list[dict]:
    """Best win per player inside one season window, ranked (fastest first)."""
    sql = _SEASON_BEST + "SELECT user_id,best_elapsed_ms,best_opened_actions,place FROM ranked ORDER BY place,user_id"
    params: tuple = (str(difficulty), starts_at, ends_at)
    if limit is not None:
        sql += " LIMIT ?"
        params += (int(limit),)
    async with db.execute(sql, params) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def win_players(db) -> int:
    async with db.execute("SELECT COUNT(DISTINCT user_id) FROM minesweeper_v2_runs WHERE status='won'") as cursor:
        return int((await cursor.fetchone())[0])


async def win_standings(db, *, limit: int, offset: int = 0) -> list[dict]:
    """All-time wins, one row per player; the game top is not tied to a season."""
    async with db.execute(
        "SELECT user_id,COUNT(*) AS wins FROM minesweeper_v2_runs WHERE status='won' "
        "GROUP BY user_id ORDER BY wins DESC,user_id ASC LIMIT ? OFFSET ?",
        (int(limit), int(offset)),
    ) as cursor:
        return [{"user_id": int(row["user_id"]), "wins": int(row["wins"])} for row in await cursor.fetchall()]


async def win_position(db, *, user_id: int) -> dict | None:
    async with db.execute(
        "WITH w AS (SELECT user_id,COUNT(*) AS wins FROM minesweeper_v2_runs WHERE status='won' GROUP BY user_id), "
        "ranked AS (SELECT user_id,wins,ROW_NUMBER() OVER (ORDER BY wins DESC,user_id ASC) AS place FROM w) "
        "SELECT place,wins FROM ranked WHERE user_id=?",
        (int(user_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return {"place": int(row["place"]), "wins": int(row["wins"])} if row else None


async def leaderboard(db, *, user_id: int, difficulty: str, starts_at, ends_at) -> dict:
    top = await season_standings(db, difficulty=difficulty, starts_at=starts_at, ends_at=ends_at, limit=20)
    players = await public_profiles.player_projection(db, user_ids=[row["user_id"] for row in top])
    public_top = [
        {"place": int(row["place"]), "best_elapsed_ms": int(row["best_elapsed_ms"]),
         "best_opened_actions": int(row["best_opened_actions"]),
         "player": players[int(row["user_id"])]}
        for row in top
    ]
    async with db.execute(
        _SEASON_BEST + "SELECT place,best_elapsed_ms,best_opened_actions FROM ranked WHERE user_id=?",
        (str(difficulty), starts_at, ends_at, int(user_id)),
    ) as cursor:
        personal = await cursor.fetchone()
    return {"top": public_top, "personal": dict(personal) if personal else None}
