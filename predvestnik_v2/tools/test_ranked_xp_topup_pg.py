#!/usr/bin/env python3
"""S28a top-up on real PostgreSQL: levels passed under the old star table get the difference, once.

    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_ranked_xp_topup_pg.py --dsn postgresql://…@127.0.0.1:55432/<empty db>
Everything runs in one transaction that is rolled back.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime, timezone

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://unused@127.0.0.1/unused")

from core import league_v1 as rules, seasons  # noqa: E402
from infrastructure.pg_adapter import PGAdapter  # noqa: E402

OLD, NEW = 983001, 983002
OLD_TABLE = {1: 60, 2: 80, 3: 100}


async def proof(db) -> None:
    from infrastructure.repositories import league_pass as pass_repo, league_v1 as repo
    from services import league_v1
    now = datetime.now(timezone.utc)
    number = seasons.season_number(now)
    season = f"s{number}"
    await pass_repo.ensure_tables(db)
    await repo.ensure_tables(db)
    levels = {   # (user, game, level): (best stars, experience the level gave)
        (OLD, "minesweeper", 1): (3, OLD_TABLE[3]),                                   # all under the old table
        (OLD, "minesweeper", 2): (1, OLD_TABLE[1]),
        (OLD, "rhythm", 1): (2, OLD_TABLE[2]),
        (OLD, "rhythm", 2): (3, OLD_TABLE[1] + rules.XP_BY_STARS[3] - rules.XP_BY_STARS[1]),   # old ★, improved after the release
        (NEW, "rhythm", 1): (3, rules.XP_BY_STARS[3]),                                # already the new table
    }
    for (user, game, level), (stars, xp) in levels.items():
        await db.execute("INSERT INTO league_demo_progress(user_id,season,game,level,stars,attempts,xp) VALUES (?,?,?,?,?,1,?)",
                         (user, season, game, level, stars, xp))
    await db.execute("INSERT INTO league_demo_progress(user_id,season,game,level,stars,attempts,xp) VALUES (?,?,?,?,?,1,?)",
                     (OLD, "demo-1", "rhythm", 1, 3, 100))   # the demo had fake experience: never topped up
    for user in (OLD, NEW):
        given = sum(xp for (u, *_), (_, xp) in levels.items() if u == user)
        await pass_repo.add_xp(db, user_id=user, season=number, xp=given)
    before = {u: await pass_repo.xp(db, user_id=u, season=number) for u in (OLD, NEW)}

    expected = sum(rules.XP_BY_STARS[stars] - xp for (u, *_), (stars, xp) in levels.items() if u == OLD)
    counted = await league_v1.topup_ranked_xp(db, apply=False, now=now)
    mine = [p for p in counted["per_player"] if p["user_id"] in (OLD, NEW)]
    assert mine == [{"user_id": OLD, "levels": 4, "xp": expected}], mine
    assert await pass_repo.xp(db, user_id=OLD, season=number) == before[OLD], "counting changes nothing"
    print(f"PASS count only: 4 levels, +{expected} experience, nothing written")

    applied = await league_v1.topup_ranked_xp(db, apply=True, now=now)
    assert [p for p in applied["per_player"] if p["user_id"] in (OLD, NEW)] == mine
    assert await pass_repo.xp(db, user_id=OLD, season=number) == before[OLD] + expected
    assert await pass_repo.xp(db, user_id=NEW, season=number) == before[NEW], "a level already on the new table gets nothing"
    rows = {(r["game"], r["level"]): r for r in await repo.progress(db, user_id=OLD, season=season)}
    assert all(rows[(g, lv)]["xp"] == rules.XP_BY_STARS[s] for (u, g, lv), (s, _) in levels.items() if u == OLD)
    demo = await repo.progress(db, user_id=OLD, season="demo-1")
    assert demo[0]["xp"] == 100, "the demo season is left alone"
    async with db.execute("SELECT COUNT(*) FROM league_pass_receipts WHERE user_id=? AND source='league_topup'", (OLD,)) as cur:
        assert (await cur.fetchone())[0] == 4
    print("PASS applied: the pass and the level rows now match the current table; the demo is untouched")

    again = await league_v1.topup_ranked_xp(db, apply=True, now=now)
    assert not [p for p in again["per_player"] if p["user_id"] in (OLD, NEW)]
    assert await pass_repo.xp(db, user_id=OLD, season=number) == before[OLD] + expected
    print("PASS a second run adds nothing")

    # A later improvement pays only the difference of the current table, as for everyone.
    assert rules.xp_gain(1, 3) == rules.XP_BY_STARS[3] - rules.XP_BY_STARS[1]
    print("PASS later improvements stay on the normal difference")


async def run(dsn: str) -> None:
    os.environ["DATABASE_URL"] = dsn
    from bot.core.database import init_db
    from bot.startup_schema import ensure_runtime_schema
    from infrastructure.database import create_pool, get_pool
    await create_pool()
    await init_db()
    await ensure_runtime_schema(get_pool())
    async with get_pool().acquire() as connection:
        db = PGAdapter(connection)
        transaction = connection.transaction()
        await transaction.start()
        try:
            await proof(db)
        finally:
            await transaction.rollback()
    print("PASS S28a top-up on PostgreSQL")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    asyncio.run(run(parser.parse_args().dsn))
