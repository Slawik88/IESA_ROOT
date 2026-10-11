#!/usr/bin/env python3
"""Real PostgreSQL proof: season windows split the board, settlement pays once."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

import asyncpg

from core import seasons as rules
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import economy_ledger
from infrastructure.repositories import minesweeper_v2 as ms_repo
from services import game_seasons
from services import minesweeper_v2 as ms

USERS = (977001, 977002, 977003)


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    await economy_ledger.ensure_tables(db)
    await ms_repo.ensure_tables(db)
    run_ids: list[str] = []
    transaction = connection.transaction()
    await transaction.start()
    try:
        async def win(user_id: int, when: datetime, elapsed_ms: int) -> None:
            run_id = str(uuid4())
            run_ids.append(run_id)
            await connection.execute(
                "INSERT INTO minesweeper_v2_runs(run_id,user_id,difficulty,ruleset_version,seed,status,opened_actions,"
                "started_at,finished_at,elapsed_ms) VALUES ($1,$2,'easy','test',$3,'won',5,$4,$4,$5)",
                run_id, user_id, b"x" * 32, when, elapsed_ms)

        s1_start, s1_end = rules.season_bounds(1)
        s2_start, _ = rules.season_bounds(2)
        during = datetime(2027, 1, 5, tzinfo=timezone.utc)
        await win(USERS[0], during, 30_000)
        await win(USERS[0], during, 20_000)   # personal best wins the place
        await win(USERS[1], during, 25_000)
        await win(USERS[2], s2_start, 1_000)  # belongs to the next season

        board1 = await ms_repo.leaderboard(db, user_id=USERS[0], difficulty="easy", starts_at=s1_start, ends_at=s1_end)
        assert board1["personal"]["best_elapsed_ms"] == 20_000, board1
        assert len(board1["top"]) == 2 and board1["top"][0]["place"] == 1, board1
        s2_end = rules.season_bounds(2)[1]
        board2 = await ms_repo.leaderboard(db, user_id=USERS[0], difficulty="easy", starts_at=s2_start, ends_at=s2_end)
        assert board2["personal"] is None and board2["top"][0]["best_elapsed_ms"] == 1_000, board2

        async def standings(db_, start, end):
            rows = await ms_repo.season_standings(db_, difficulty="easy", starts_at=start, ends_at=end)
            return [r for r in rows if int(r["user_id"]) in USERS]

        async def mora_of(user_id: int) -> int:
            async with db.execute("SELECT COALESCE(SUM(delta),0) FROM economic_ledger "
                                  "WHERE user_id=? AND currency='mora' AND reason_code='season_reward'", (user_id,)) as cursor:
                row = await cursor.fetchone()
            return int(row[0])

        now = datetime(2027, 6, 1, tzinfo=timezone.utc)  # season 2 is running
        first = await game_seasons.settle_due(db, game="minesweeper", board="easy", standings=standings, now=now)
        again = await game_seasons.settle_due(db, game="minesweeper", board="easy", standings=standings, now=now)
        assert first == 1 and again == 0, (first, again)
        last = await game_seasons.last_result(db, game="minesweeper", board="easy", user_id=USERS[0])
        assert last["season"] == 1 and last["place"] == 1 and last["reward_mora"] == 1500, last
        second = await game_seasons.last_result(db, game="minesweeper", board="easy", user_id=USERS[1])
        assert second["place"] == 2 and second["reward_mora"] == 1000, second
        assert await game_seasons.last_result(db, game="minesweeper", board="easy", user_id=USERS[2]) is None
        assert await mora_of(USERS[0]) == 1500 and await mora_of(USERS[1]) == 1000
    finally:
        await transaction.rollback()
        await connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
print("game seasons: PostgreSQL window split, settlement and one-time reward OK")
