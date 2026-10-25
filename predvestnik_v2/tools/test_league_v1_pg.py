#!/usr/bin/env python3
"""Real PostgreSQL proof of the League demo: early access gate, server-side Minesweeper, Rhythm journals, stars.

Run: PYTHONPATH=. python3 tools/test_league_v1_pg.py --dsn postgresql://postgres@127.0.0.1:55432/league_test
Uses a disposable loopback database; the League tables are dropped first.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from urllib.parse import urlparse

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://unused@127.0.0.1/unused")

import asyncpg  # noqa: E402

from core import league_v1 as rules
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import league_v1 as repo
from infrastructure.repositories import public_profiles_v1 as public_profiles
from services import admin_access, early_access, league_rhythm, league_v1 as league

TESTER, PLAYER = 910_001, 910_002


def local_dsn(value: str) -> str:
    if urlparse(value).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def setup(db) -> None:
    for table in ("league_demo_runs", "league_demo_progress", "admin_role_grants"):
        await db.execute(f"DROP TABLE IF EXISTS {table}")
    await db.execute("CREATE TABLE IF NOT EXISTS users (user_tg_id BIGINT PRIMARY KEY, user_tg_username TEXT, bot_rank INT DEFAULT 0)")
    await db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS bot_rank SMALLINT DEFAULT 0")   # bot/chat/schema.py on a full schema
    await db.execute("DELETE FROM users WHERE user_tg_id IN (?,?)", (TESTER, PLAYER))
    await db.execute("INSERT INTO users(user_tg_id,user_tg_username,bot_rank) VALUES (?,?,1),(?,?,0)", (TESTER, "tester", PLAYER, "player"))
    await public_profiles.ensure_tables(db)
    admin_access._ready = False
    await admin_access.ensure_schema(db)


async def gate(db) -> None:
    assert not await early_access.allowed(db, TESTER), "by default only the creator has early access"
    await db.execute("INSERT INTO admin_role_grants(key,min_rank,updated_by) VALUES (?,1,1)", (rules.FLAG_KEY,))
    assert await early_access.allowed(db, TESTER) and not await early_access.allowed(db, PLAYER)
    await db.execute("UPDATE admin_role_grants SET min_rank=0 WHERE key=?", (rules.FLAG_KEY,))
    assert not await early_access.allowed(db, PLAYER), "the threshold never drops below the tester role"


async def board_of(db, run_id: str) -> dict:
    async with db.execute("SELECT board_json FROM league_demo_runs WHERE run_id=?", (run_id,)) as cursor:
        return repo.load((await cursor.fetchone())[0])


async def clear(db, view: dict, *, wrong_flag: bool = False) -> dict:
    board = await board_of(db, view["run_id"])
    mines = set(board["mines"])
    assert not view["mines"] and set(map(int, view["cells"])).isdisjoint(mines), "the board never reaches the phone"
    if wrong_flag:
        safe = next(c for c in range(board["width"] * board["height"]) if c not in mines and str(c) not in view["cells"])
        view = await league.mines_act(db, user_id=TESTER, run_id=view["run_id"], revision=view["revision"], kind="flag", cell=safe)
        view = await league.mines_act(db, user_id=TESTER, run_id=view["run_id"], revision=view["revision"], kind="flag", cell=safe)
    for cell in range(board["width"] * board["height"]):
        if cell not in mines and str(cell) not in view["cells"] and view["status"] == "active":
            view = await league.mines_act(db, user_id=TESTER, run_id=view["run_id"], revision=view["revision"], kind="open", cell=cell)
    return view


async def minesweeper(db) -> None:
    try:
        await league.start(db, user_id=TESTER, game="minesweeper", level=2)
    except league.LeagueError:
        pass
    else:
        raise AssertionError("a locked level must not start")
    won = await clear(db, await league.start(db, user_id=TESTER, game="minesweeper", level=1))
    assert won["status"] == "won" and won["result"]["stars"] == 3 and won["result"]["xp"] == 100, won["result"]
    flagged = await clear(db, await league.start(db, user_id=TESTER, game="minesweeper", level=2), wrong_flag=True)
    assert flagged["result"]["stars"] == 1 and flagged["wrong_flags"] == 1 and flagged["result"]["xp"] == 60
    again = await clear(db, await league.start(db, user_id=TESTER, game="minesweeper", level=2))
    assert again["result"]["stars"] == 3 and again["result"]["xp"] == 40, "only the improvement adds experience"
    view = await league.start(db, user_id=TESTER, game="minesweeper", level=3)
    stale = await league.mines_act(db, user_id=TESTER, run_id=view["run_id"], revision=view["revision"] + 5, kind="open", cell=0)
    assert stale.get("stale") and stale["revision"] == view["revision"]
    mine = (await board_of(db, view["run_id"]))["mines"][0]
    lost = await league.mines_act(db, user_id=TESTER, run_id=view["run_id"], revision=view["revision"], kind="open", cell=mine)
    assert lost["status"] == "lost" and lost["result"]["stars"] == 0 and lost["mines"]
    replaced = await league.start(db, user_id=TESTER, game="minesweeper", level=3)
    newer = await league.start(db, user_id=TESTER, game="minesweeper", level=3)
    old = await league.mines_act(db, user_id=TESTER, run_id=replaced["run_id"], revision=replaced["revision"], kind="open", cell=0)
    assert old["status"] == "cancelled" and newer["status"] == "active", "a new start closes the previous attempt"


async def rhythm(db) -> None:
    packet = await league.start(db, user_id=TESTER, game="rhythm", level=1)
    assert "seed" not in packet and len(packet["runes"]) == packet["signals"]
    async with db.execute("SELECT board_json FROM league_demo_runs WHERE run_id=?", (packet["run_id"],)) as cursor:
        stored = league.repo.load((await cursor.fetchone())["board_json"])
    assert stored == {"gifts": rules.GIFT_POOL_NOW}, "a rhythm level remembers the gift pool it was started with"
    assert any(item["id"] == "phoenix" for item in packet["catalog"]), "the phone receives the whole catalog, new gifts included"
    journal = [{"kind": "tap", "signal_no": n, "rune": r, "elapsed_ms": 260 + n * 37 % 90} for n, r in enumerate(packet["runes"], 1)]
    for draft in range(len(packet["drafts"]), 0, -1):   # skip every gift: the score must equal the reference
        journal.insert(draft * rules.RHYTHM_CHUNK, {"kind": "pick", "perk_id": None})
    try:
        await league.rhythm_finish(db, user_id=TESTER, run_id=packet["run_id"], actions=journal)
    except league.LeagueError as exc:
        assert "быстрее" in str(exc), str(exc)
    else:
        raise AssertionError("a level returned faster than it can be played must be refused")
    await db.execute("UPDATE league_demo_runs SET started_at=started_at-INTERVAL '2 minutes' WHERE run_id=?", (packet["run_id"],))
    result = await league.rhythm_finish(db, user_id=TESTER, run_id=packet["run_id"], actions=journal)
    assert result["stars"] == 3 and result["detail"]["score"] == packet["reference"] and result["xp"] == 100, result
    assert result["detail"]["review"] == [], "an ordinary human-paced run is never marked"
    replay = await league.rhythm_finish(db, user_id=TESTER, run_id=packet["run_id"], actions=journal)
    assert replay["replay"] and replay["xp"] == 100, "a repeated upload returns the stored result, nothing is added"
    assert league_rhythm.played_ms({"_taps": [(300, True, True)] * 30}) == 9000


async def overview_and_reset(db) -> None:
    me = await league.overview(db, user_id=TESTER)
    mines, rh = me["games"]["minesweeper"], me["games"]["rhythm"]
    assert mines["unlocked"] == 3 and mines["stars"] == 6 and rh["unlocked"] == 2, (mines, rh)
    assert me["pass"]["xp"] == 300 and me["pass"]["level"] == 1 and me["pass"]["fake"]
    assert mines["top"][0]["me"] and mines["top"][0]["level"] == 2
    assert me["games"]["minesweeper"]["levels"]["3"]["attempts"] == 2, "a loss and an attempt closed by a new start; the open one is not counted yet"
    await league.reset(db, user_id=TESTER)
    assert (await league.overview(db, user_id=TESTER))["games"]["minesweeper"]["unlocked"] == 1


async def real_season(db) -> None:
    """After the switch: the League is public, its season is real and a level feeds the season pass."""
    from infrastructure.repositories import league_pass as pass_repo
    await pass_repo.ensure_tables(db)
    original = league._season
    league._season = lambda now=None: "s2"
    try:
        won = await clear(db, await league.start(db, user_id=TESTER, game="minesweeper", level=1))
        assert won["result"]["stars"] == 3 and won["result"]["xp"] == 100
        assert await pass_repo.xp(db, user_id=TESTER, season=2) == 100, "a real season level feeds the pass"
        me = await league.overview(db, user_id=TESTER)
        assert me["demo"] is False and me["pass"] is None and me["games"]["minesweeper"]["unlocked"] == 2
        try:
            await league.reset(db, user_id=TESTER)
        except league.LeagueError:
            pass
        else:
            raise AssertionError("a real season can never be reset")
    finally:
        league._season = original
    assert rules.season_key(rules.seasons.SEASON_TWO_START) == "s2" and rules.is_public(rules.seasons.SEASON_TWO_START)


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    league._season = lambda now=None: rules.DEMO_SEASON   # fixed clock: the demo before season 2
    try:
        await setup(db)
        await gate(db)
        await minesweeper(db)
        await rhythm(db)
        await overview_and_reset(db)
        await real_season(db)
    finally:
        await connection.close()
    print("PASS league demo on PostgreSQL: gate, server Minesweeper, Rhythm journals, stars, experience, reset")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, required=True)
    asyncio.run(run(parser.parse_args().dsn))
