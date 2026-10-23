#!/usr/bin/env python3
"""Real PostgreSQL proof of the season pass from season 2: experience, casual cap, claims, VIP row, grants.

Run: PYTHONPATH=. python3 tools/test_league_pass_pg.py --dsn postgresql://postgres@127.0.0.1:55432/<empty db>
Everything runs in one transaction that is rolled back.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta
import os

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://unused@127.0.0.1/unused")

from core import league_pass as rules, seasons  # noqa: E402
from infrastructure.pg_adapter import PGAdapter  # noqa: E402
from infrastructure.repositories import chests_v1 as chests_repo, economy_ledger  # noqa: E402
from infrastructure.repositories import league_pass as repo  # noqa: E402
from services import league_pass as service  # noqa: E402

PLAYER, VIP, NEWBIE = 981001, 981002, 981003
S2 = seasons.season_bounds(2)[0]
DAY = S2 + timedelta(days=3, hours=12)


async def setup(db) -> None:
    await economy_ledger.ensure_tables(db)
    await chests_repo.ensure_tables(db)
    await repo.ensure_tables(db)
    old = S2 - timedelta(days=90)
    for user in (PLAYER, VIP, NEWBIE):
        await db.execute("INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user,))
    for user in (PLAYER, VIP):
        await db.execute("INSERT INTO user_chat_stats(user_tg_id, chat_tg_id, joined_at, membership_since) VALUES (?,1,?,?) "
                         "ON CONFLICT DO NOTHING", (user, old.replace(tzinfo=None), old))
    await db.execute("INSERT INTO vip_subscriptions(user_id, tier, expires_at) VALUES (?,'gold',NOW()+INTERVAL '3650 days') "
                     "ON CONFLICT DO NOTHING", (VIP,))


async def balance(db, user: int, currency: str) -> int:
    async with db.execute("SELECT COALESCE(SUM(delta),0) FROM economic_ledger WHERE user_id=? AND currency=? AND reason_code=?",
                          (user, currency, rules.REASON)) as cursor:
        return int((await cursor.fetchone())[0])


async def keys(db, user: int) -> dict[str, int]:
    async with db.execute("SELECT source_kind, COUNT(*) FROM chest_key_grants_v1 WHERE user_id=? GROUP BY source_kind", (user,)) as cursor:
        return {str(r[0]): int(r[1]) for r in await cursor.fetchall()}


async def experience(db) -> None:
    before = S2 - timedelta(hours=1)
    assert await service.record_mines(db, user_id=PLAYER, run_id="old", won=True, difficulty="hard", at=before) == 0, \
        "season 1 belongs to the old pass"
    assert await service.record_mines(db, user_id=PLAYER, run_id="m1", won=True, difficulty="hard", at=DAY) == 40
    assert await service.record_mines(db, user_id=PLAYER, run_id="m1", won=True, difficulty="hard", at=DAY) == 0, "one game counts once"
    assert await service.record_mines(db, user_id=PLAYER, run_id="m2", won=False, difficulty="hard", at=DAY) == 0
    assert await service.record_rhythm(db, user_id=PLAYER, run_id="r1", score=900_000, at=DAY) == rules.RHYTHM_MAX_XP
    added = [await service.record_rhythm(db, user_id=PLAYER, run_id=f"r{i}", score=30_000, at=DAY) for i in range(2, 12)]
    assert sum(added) == rules.CASUAL_DAILY_CAP - 40 - rules.RHYTHM_MAX_XP and added[-1] == 0, added
    assert await service.record_rhythm(db, user_id=PLAYER, run_id="next-day", score=30_000, at=DAY + timedelta(days=1)) == 60
    # the result screen line «+N опыта Пропуска»: what one game gave, 0 once the day was full, nothing for a loss
    line = await service.casual_receipt(db, user_id=PLAYER, source="minesweeper", event_id="m1", now=DAY)
    assert line["active"] and line["counted"] and line["xp"] == 40 and line["today"] == rules.CASUAL_DAILY_CAP, line
    assert (await service.casual_receipt(db, user_id=PLAYER, source="rhythm", event_id="r11", now=DAY))["xp"] == 0
    assert (await service.casual_receipt(db, user_id=PLAYER, source="rhythm", event_id="r11", now=DAY))["counted"]
    assert not (await service.casual_receipt(db, user_id=PLAYER, source="minesweeper", event_id="m2", now=DAY))["counted"]
    assert (await service.casual_receipt(db, user_id=PLAYER, source="minesweeper", event_id="m1", now=before)) == {"active": False}
    gained = await service.add_xp(db, user_id=PLAYER, source="league", event_id="s2:minesweeper:1:3", xp=2_000, casual=False, at=DAY)
    assert gained == 2_000, "League levels are not limited by the casual cap"
    assert await repo.xp(db, user_id=PLAYER, season=2) == rules.CASUAL_DAILY_CAP + 60 + 2_000
    await service.add_xp(db, user_id=VIP, source="league", event_id="v", xp=rules.XP_PER_LEVEL * rules.LEVELS, casual=False, at=DAY)
    await service.add_xp(db, user_id=NEWBIE, source="league", event_id="n", xp=900, casual=False, at=DAY)


async def claims(db) -> None:
    state = await service.status(db, user_id=PLAYER, now=DAY)
    season = state["seasons"][-1]
    assert state["active"] and not state["vip"] and season["level"] == 7 and season["track"][0]["vip"]["state"] == "vip"
    result = await service.claim(db, user_id=PLAYER, season=2, now=DAY)
    assert [g["level"] for g in result["granted"]] == list(range(1, 8)) and {g["track"] for g in result["granted"]} == {"free"}
    assert await balance(db, PLAYER, "mora") == 100 + 100 + 150 and await balance(db, PLAYER, "zarniki") == 5
    assert await balance(db, PLAYER, "diamonds") == 0 and await keys(db, PLAYER) == {"pass_tier1": 2, "pass_tier3": 1}
    try:
        await service.claim(db, user_id=PLAYER, season=2, now=DAY)
    except service.PassError:
        pass
    else:
        raise AssertionError("a second claim without new levels must be refused")
    vip = await service.claim(db, user_id=VIP, season=2, now=DAY)
    assert len(vip["granted"]) == 2 * rules.LEVELS
    assert await balance(db, VIP, "zarniki") == 30 + 80, "the owner's caps: 30 free and 80 VIP Zarniki a season"
    tiers = await keys(db, VIP)
    assert tiers["pass_tier6"] == 3 and sum(tiers.values()) == sum("key" in r for rows in rules.TRACK.values() for r in rows)
    from services import chests_v1 as chests
    view = await chests.overview(db, user_id=VIP)
    assert view["key_balances"]["6"] == 3 and view["key_balances"]["4"] >= 1, view["key_balances"]
    opened = await chests.prepare_free_open(db, user_id=VIP, action_id="pass-key-open", key_tier=6,
                                            requested_catalog_version=view["catalog_version"], requested_catalog_digest=view["catalog_digest"])
    print("chest opened with a pass key:", {k: opened[k] for k in opened if k in ("key_tier", "stars", "status")})
    assert opened, "a pass key opens a chest like any other key"
    try:
        await service.claim(db, user_id=NEWBIE, season=2, now=DAY)
    except service.PassError as exc:
        assert "14" in str(exc)
    else:
        raise AssertionError("an account younger than 14 days cannot claim")
    late = seasons.season_bounds(2)[1] + rules.CLAIM_GRACE + timedelta(minutes=1)
    try:
        await service.claim(db, user_id=NEWBIE, season=2, now=late)
    except service.PassError as exc:
        assert "нельзя" in str(exc)
    else:
        raise AssertionError("the claim window closes 30 days after the season")


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
            await setup(db)
            await experience(db)
            await claims(db)
        finally:
            await transaction.rollback()
    print("PASS season pass 2 on PostgreSQL: experience, casual cap, claims, VIP row, Mora/Diamonds/Zarniki/keys, deadlines")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    asyncio.run(run(parser.parse_args().dsn))
