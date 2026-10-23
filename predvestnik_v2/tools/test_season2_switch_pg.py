#!/usr/bin/env python3
"""Dress rehearsal of the 25.10.2026 switch on the full project schema, with the clock set to that night.

Season 1 places are frozen and paid an hour after the switch, a forged phone journal is held for review
instead of taking first place, the League opens to everyone and the new pass starts.
Run: PYTHONPATH=. python3 tools/test_season2_switch_pg.py --dsn postgresql://postgres@127.0.0.1:55432/<empty db>
Everything runs in one transaction that is rolled back.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta
import os
import random
from uuid import uuid4

os.environ.setdefault("BOT_TOKEN", "1:x")

from core import league_v1 as league_rules, seasons  # noqa: E402
from core import rhythm_v2 as rhythm_rules  # noqa: E402
from infrastructure.pg_adapter import PGAdapter  # noqa: E402
from infrastructure.repositories import rhythm_v2 as rhythm_repo  # noqa: E402

PLAYERS = list(range(990_001, 990_013))
CHEAT, PAUSER = PLAYERS[0], PLAYERS[1]
S1_START, SWITCH = seasons.season_bounds(1)[0], seasons.season_bounds(2)[0]


def journal(seed: bytes, rng: random.Random, *, forged: bool, pauses: int = 0) -> list[dict]:
    taps = []
    for n in range(1, 61):
        rune = rhythm_rules.expected_rune(seed, n)
        if forged:
            taps.append({"kind": "tap", "signal_no": n, "rune": rune, "elapsed_ms": 30})
        else:
            wrong = rng.random() < 0.04
            taps.append({"kind": "tap", "signal_no": n, "rune": rng.choice([r for r in rhythm_rules.RUNES if r != rune]) if wrong else rune,
                         # after a resume the rune seen before the pause returns: one instant honest tap per pause
                         "elapsed_ms": 40 if n <= pauses else int(rng.lognormvariate(6.2, 0.22))})
    return taps


async def season_one(db) -> None:
    await rhythm_repo.ensure_tables(db)
    rng = random.Random(25)
    for user in PLAYERS:
        await db.execute("INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user,))
        await db.execute("INSERT INTO user_chat_stats(user_tg_id, chat_tg_id, joined_at, membership_since) VALUES (?,1,?,?) "
                         "ON CONFLICT DO NOTHING", (user, (S1_START - timedelta(days=60)).replace(tzinfo=None), S1_START - timedelta(days=60)))
        for k in range(5):
            run_id, seed = str(uuid4()), rng.randbytes(32)
            forged = user == CHEAT and k == 0
            score = 900_000 if forged else 40_000 + 1000 * PLAYERS.index(user) + k
            when = S1_START + timedelta(days=2 + k % 3, hours=k)
            await db.connection.execute(
                "INSERT INTO rhythm_v2_runs(run_id,user_id,mode,ruleset_version,seed,offers_json,status,health,score,"
                "integrity_status,integrity_reason,created_at,finished_at) "
                "VALUES ($1,$2,'normal','rhythm-v2-rules-6',$3,'{}'::jsonb,'finished',0,$4,'clear','resilient-local-v1',$5,$5)",
                run_id, user, seed, score, when)
            await rhythm_repo.insert_action(db, run_id=run_id, action_id="local:result:v1",
                                            request={"protocol": "resilient-local-v1", "actions": journal(seed, rng, forged=forged, pauses=12 if user == PAUSER else 0)},
                                            result={"score": score})


async def mora_paid(db, user: int) -> int:
    async with db.execute("SELECT COALESCE(SUM(delta),0) FROM economic_ledger WHERE user_id=? AND reason_code='season_reward'", (user,)) as c:
        return int((await c.fetchone())[0])


async def settlement(db) -> None:
    from services import game_seasons, rhythm_v2
    boards = {("rhythm", "normal"): rhythm_v2.season_standings}
    early = await game_seasons.settle_due(db, boards=boards, now=SWITCH + timedelta(minutes=50))
    assert early == {"snapshots": 0, "paid": 0, "failed": 0, "closed": 0}, early
    done = await game_seasons.settle_due(db, boards=boards, now=SWITCH + timedelta(minutes=70))
    assert done["snapshots"] == 1 and done["closed"] == 1 and done["failed"] == 0 and done["paid"] == len(PLAYERS) - 1, done
    async with db.execute("SELECT integrity_status, integrity_reason FROM rhythm_v2_runs WHERE user_id=? AND score=900000", (CHEAT,)) as c:
        row = await c.fetchone()
    assert row[0] == "review_required" and row[1].startswith("auto_screen:"), tuple(row)
    async with db.execute("SELECT COUNT(*) FROM rhythm_v2_runs WHERE user_id=? AND integrity_status='clear'", (PAUSER,)) as c:
        assert (await c.fetchone())[0] == 5, "a player who paused a dozen times is not held"
    assert await mora_paid(db, CHEAT) == 0, "four honest runs are below the participation terms: nothing for the forger"
    best = PLAYERS[-1]
    assert await mora_paid(db, best) == seasons.reward(1)[0], "the best honest player gets first place"
    again = await game_seasons.settle_due(db, boards=boards, now=SWITCH + timedelta(hours=3))
    assert again == {"snapshots": 0, "paid": 0, "failed": 0, "closed": 0}, "a closed season is never paid twice"


async def opening(db) -> None:
    from services import league_pass, league_v1 as league, season_pass
    now = SWITCH + timedelta(minutes=5)
    assert league_rules.is_public(now) and league_rules.season_key(now) == "s2" and seasons.season_number(now) == 2
    original = league._season
    league._season = lambda moment=None: league_rules.season_key(now)
    try:
        me = await league.overview(db, user_id=PLAYERS[3])
        assert me["demo"] is False and me["season"] == "s2" and me["games"]["minesweeper"]["unlocked"] == 1
    finally:
        league._season = original
    state = await league_pass.status(db, user_id=PLAYERS[3], now=now)
    assert state["active"] and [s["season"] for s in state["seasons"]] == [2] and state["seasons"][0]["current"]
    assert await league_pass.record_mines(db, user_id=PLAYERS[3], run_id="first-s2", won=True, difficulty="normal", at=now) == 20
    assert await season_pass.record_game(db, user_id=PLAYERS[3], source="rhythm", event_id="old-pass", points=10, occurred_at=now) == 0


async def run(dsn: str) -> None:
    os.environ["DATABASE_URL"] = dsn
    from bot.core.database import init_db
    from bot.startup_schema import ensure_runtime_schema
    from infrastructure.database import create_pool, get_pool
    from infrastructure.repositories import economy_ledger, league_pass, league_v1, public_profiles_v1, quests_v1, skins_v3, system_flags
    await create_pool()
    await init_db()
    await ensure_runtime_schema(get_pool())
    async with get_pool().acquire() as connection:
        db = PGAdapter(connection)
        for ensure in (economy_ledger.ensure_tables, skins_v3.ensure_tables, quests_v1.ensure_tables, public_profiles_v1.ensure_tables,
                       league_pass.ensure_tables, league_v1.ensure_tables):
            await ensure(db)
        await system_flags.ensure_table(db)
        transaction = connection.transaction()
        await transaction.start()
        try:
            await season_one(db)
            await settlement(db)
            await opening(db)
        finally:
            await transaction.rollback()
    print("PASS switch rehearsal: season 1 frozen and paid at 01:00 UTC, forged journal held, League and new pass open")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    asyncio.run(run(parser.parse_args().dsn))
