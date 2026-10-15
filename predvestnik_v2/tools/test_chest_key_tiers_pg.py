#!/usr/bin/env python3
"""Real PostgreSQL proof for ECO-04 PR-A keys by stars (key tiers and offers)."""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import pathlib
import sys
import time
from urllib.parse import urlparse

import asyncpg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.chests_v1 import (
    CATALOG_VERSION, KEY_OFFERS, KEY_OFFERS_FLAG, catalog_digest, canonical_snapshot_fingerprint,
)
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import chests_v1 as repo
from infrastructure.repositories import skins_v3 as essence_repo
from infrastructure.repositories import system_flags
from services import chests_v1


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


def cat() -> dict:
    return dict(requested_catalog_version=CATALOG_VERSION, requested_catalog_digest=catalog_digest())


async def scalar(db, sql: str, params: tuple = ()):
    async with db.execute(sql, params) as cursor:
        row = await cursor.fetchone()
    return row[0] if row else None


async def fund(db, user: int, *, mora=0, diamonds=0, zarniki=0, essence=0) -> None:
    await db.execute(
        "INSERT INTO users(user_tg_id,user_balance_mora,user_balance_diamonds,user_balance_zarniki) "
        "VALUES (?,?,?,?) ON CONFLICT(user_tg_id) DO UPDATE SET user_balance_mora=EXCLUDED.user_balance_mora,"
        "user_balance_diamonds=EXCLUDED.user_balance_diamonds,user_balance_zarniki=EXCLUDED.user_balance_zarniki",
        (user, mora, diamonds, zarniki),
    )
    if essence:
        await essence_repo.essence_apply(db, user, essence, reason="test", reference=None,
                                         idempotency_key=f"test-essence:{user}:{time.time_ns()}")


async def balances(db, user: int) -> tuple:
    async with db.execute(
        "SELECT user_balance_mora,user_balance_diamonds,user_balance_zarniki FROM users WHERE user_tg_id=?", (user,),
    ) as cursor:
        row = await cursor.fetchone()
    return float(row[0]), float(row[1]), float(row[2]), await essence_repo.essence_balance(db, user)


async def buy(db, user: int, offer: str, action: str) -> dict:
    return await chests_v1.buy_offer(db, user_id=user, offer_id=offer, action_id=action, **cat())


async def refused(coro, text: str = "") -> str:
    try:
        await coro
    except chests_v1.ChestKeyConflict as exc:
        assert text in str(exc), (text, str(exc))
        return str(exc)
    raise AssertionError(f"expected a refusal: {text}")


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    tx = connection.transaction()
    await tx.start()
    real_window = repo.offer_window
    try:
        db = PGAdapter(connection)
        await essence_repo.ensure_tables(db)
        for flag in ("content_chests_v1", "game_rhythm_v2", "game_minesweeper_v2"):  # a fresh test DB has them off
            await system_flags.set_flag(db, flag, True)
        await system_flags.set_flag(db, KEY_OFFERS_FLAG, False)
        user = 992_000_001
        await fund(db, user, mora=100_000, diamonds=100, zarniki=10_000, essence=1_000)

        # Flag off: offers refused and hidden, the legacy 10 ✨ tier-1 purchase still works.
        await refused(buy(db, user, "bronze_mora", "off-1"), "недоступны")
        view = await chests_v1.overview(db, user_id=user)
        assert view["offers"] == [] and view["tiers_enabled"] is False and view["funding"]["paid"] is True
        legacy = await chests_v1.purchase_key(db, user_id=user, action_id="legacy-1", **cat())
        assert legacy["applied"] and (await repo.tier_balances(db, user))[1] == 1

        # Flag on: legacy purchase refused, offers on sale with real odds per tier.
        await system_flags.set_flag(db, KEY_OFFERS_FLAG, True)
        await refused(chests_v1.purchase_key(db, user_id=user, action_id="legacy-2", **cat()), "Серебряным")
        view = await chests_v1.overview(db, user_id=user)
        odds = {row["tier"]: row["star_odds"][0] for row in view["key_tiers"]}
        assert odds[3]["percent"] == 80.0 and odds[4]["percent"] == 89.0 and odds[6]["percent"] == 97.0
        assert {row["offer_id"] for row in view["offers"]} == set(KEY_OFFERS)
        silver = next(row for row in view["offers"] if row["offer_id"] == "silver_zarniki")
        assert silver["used"] == 1 and silver["remaining"] == 1, silver  # legacy key of today counts

        # Each of the five limit counters, with a UTC day/week boundary via a fixed window.
        monday, sunday = dt.date(2026, 10, 12), dt.date(2026, 10, 18)
        windows = {"now": (monday, monday)}

        async def fixed_window(_db):
            return windows["now"]

        repo.offer_window = fixed_window
        limits = {"bronze_mora": 3, "silver_craft": 1, "platinum_diamonds": 1, "platinum_zarniki": 1}
        for offer, limit in limits.items():
            for index in range(limit):
                assert (await buy(db, user, offer, f"{offer}-{index}"))["applied"]
            await refused(buy(db, user, offer, f"{offer}-over"), "Лимит")
        # silver ✨: 2 per UTC day (legacy keys are on the real day, not this fixed one)
        for index in range(2):
            assert (await buy(db, user, "silver_zarniki", f"silver-{index}"))["applied"]
        await refused(buy(db, user, "silver_zarniki", "silver-over"), "сегодня")
        # Next UTC day, same week: daily counters reset, weekly ones do not.
        windows["now"] = (monday + dt.timedelta(days=1), monday)
        assert (await buy(db, user, "silver_zarniki", "silver-d2"))["applied"]
        assert (await buy(db, user, "platinum_zarniki", "plat-z-d2"))["applied"]
        await refused(buy(db, user, "bronze_mora", "bronze-d2"), "неделе")
        await refused(buy(db, user, "platinum_diamonds", "plat-d-d2"), "неделе")
        # Sunday is still the same ISO week; Monday of the next week resets it.
        windows["now"] = (sunday, monday)
        await refused(buy(db, user, "silver_craft", "craft-sun"), "неделе")
        windows["now"] = (sunday + dt.timedelta(days=1), sunday + dt.timedelta(days=1))
        assert (await buy(db, user, "silver_craft", "craft-next-week"))["applied"]
        assert (await buy(db, user, "bronze_mora", "bronze-next-week"))["applied"]

        # Replay: same action → same receipt and no second debit; another offer → conflict.
        before = await balances(db, user)
        replay = await buy(db, user, "bronze_mora", "bronze-next-week")
        assert replay["applied"] is False and await balances(db, user) == before
        assert replay["price"] == KEY_OFFERS["bronze_mora"]["price"]  # stored receipt price
        await refused(buy(db, user, "silver_craft", "bronze-next-week"), "action_id")

        # Shortage of either currency debits nothing and names what is missing.
        poor = 992_000_002
        await fund(db, poor, mora=5_000, essence=50)
        message = await refused(buy(db, poor, "silver_craft", "poor-craft"), "Эссенции")
        assert "Моры" not in message
        await fund(db, poor, mora=100, essence=0)
        await essence_repo.essence_apply(db, poor, 500, reason="test", reference=None, idempotency_key="poor-ess")
        message = await refused(buy(db, poor, "silver_craft", "poor-craft-2"), "Моры")
        assert "Эссенции" not in message
        await fund(db, poor, mora=2_000, diamonds=4)
        await refused(buy(db, poor, "platinum_diamonds", "poor-plat"), "💎")
        assert await balances(db, poor) == (2000.0, 4.0, 0.0, 550)
        await fund(db, poor, mora=799.5)  # fractional shortage rounds up, never "0"
        await refused(buy(db, poor, "bronze_mora", "poor-bronze"), "Не хватает: 1 Моры")
        assert await repo.get_balance(db, poor) == 0

        # Debits match the price table exactly.
        rich = 992_000_003
        await fund(db, rich, mora=10_000, diamonds=10, zarniki=1_000, essence=300)
        windows["now"] = (monday, monday)
        start = await balances(db, rich)
        for offer in KEY_OFFERS:
            await buy(db, rich, offer, f"rich-{offer}")
        end = await balances(db, rich)
        spent = {c: sum(int(o["price"].get(c, 0)) for o in KEY_OFFERS.values())
                 for c in ("mora", "diamonds", "zarniki", "essence")}
        assert (start[0] - end[0], start[1] - end[1], start[2] - end[2], start[3] - end[3]) == (
            spent["mora"], spent["diamonds"], spent["zarniki"], spent["essence"]), (start, end, spent)
        tiers = await repo.tier_balances(db, rich)
        assert tiers == {1: 0, 3: 1, 4: 2, 6: 2}, tiers
        repo.offer_window = real_window

        # One shared ✨ daily limit both ways: Silver 120 ✨ bought today blocks legacy 10 ✨ keys
        # if the flag goes back off the same UTC day.
        both = 992_000_004
        await fund(db, both, zarniki=1_000)
        for index in range(2):
            assert (await buy(db, both, "silver_zarniki", f"both-silver-{index}"))["applied"]
        await system_flags.set_flag(db, KEY_OFFERS_FLAG, False)
        assert (await chests_v1.overview(db, user_id=both))["funding"]["remaining_today"] == 0
        await refused(chests_v1.purchase_key(db, user_id=both, action_id="both-legacy", **cat()), "два ключа")
        await system_flags.set_flag(db, KEY_OFFERS_FLAG, True)

        # Opening: tier N spends tier N (FIFO), never yields fewer than N stars.
        await refused(chests_v1.prepare_free_open(db, user_id=poor, action_id="none", key_tier=3, **cat()),
                      "Нужен один ключ")
        epoch = int((await repo.lock_account(db, rich))["account_epoch"])
        first_six = await repo.next_unspent_grant(db, user_id=rich, account_epoch=epoch, key_tier=6)
        opened = await chests_v1.prepare_free_open(db, user_id=rich, action_id="open-6a", key_tier=6, **cat())
        assert opened["key_tier"] == 6
        assert await scalar(db, "SELECT grant_id FROM chest_key_allocations_v1 WHERE open_id=?",
                            (opened["open_id"],)) == first_six["id"]
        assert await scalar(db, "SELECT stars FROM chest_opens_v1 WHERE id=?", (opened["open_id"],)) >= 6
        await refused(chests_v1.prepare_free_open(db, user_id=rich, action_id="open-6a", key_tier=4, **cat()),
                      "action_id")
        assert (await chests_v1.prepare_free_open(db, user_id=rich, action_id="open-6a", key_tier=6, **cat())
                )["open_id"] == opened["open_id"]
        revealed = await chests_v1.reveal(db, user_id=rich, open_id=opened["open_id"])
        assert revealed["key_tier"] == 6 and revealed["stars"] >= 6
        open3 = await chests_v1.prepare_free_open(db, user_id=rich, action_id="open-3", key_tier=3, **cat())
        assert await scalar(db, "SELECT stars FROM chest_opens_v1 WHERE id=?", (open3["open_id"],)) >= 3
        await refused(chests_v1.prepare_free_open(db, user_id=rich, action_id="open-3b", key_tier=3, **cat()),
                      "Нет ключа этого уровня")
        assert await repo.tier_balances(db, rich) == {1: 0, 3: 0, 4: 2, 6: 1}

        # Tier-1 opens keep the pre-tier request hash, so retries from before the deploy replay.
        legacy_open = await chests_v1.prepare_free_open(db, user_id=user, action_id="open-legacy", **cat())
        expected = canonical_snapshot_fingerprint({"funding": "free_key", "catalog_version": CATALOG_VERSION,
                                                   "catalog_digest": catalog_digest()})
        assert await scalar(db, "SELECT request_hash FROM chest_opens_v1 WHERE id=?",
                            (legacy_open["open_id"],)) == expected
        assert legacy_open["key_tier"] == 1

        # An open prepared before a catalog change still reveals afterwards.
        real_digest = chests_v1.catalog_digest
        chests_v1.catalog_digest = lambda: "f" * 64
        try:
            assert (await chests_v1.reveal(db, user_id=user, open_id=legacy_open["open_id"]))["revealed"]
        finally:
            chests_v1.catalog_digest = real_digest

        # Integrity: tier counts add up to the account balance for every touched user.
        for who in (user, poor, rich):
            assert sum((await repo.tier_balances(db, who)).values()) == await repo.get_balance(db, who), who
    finally:
        repo.offer_window = real_window
        await tx.rollback()
        await connection.close()

    await race(dsn)
    print("OK: key tiers — five limit counters on UTC day/week, FIFO per tier, stars ≥ tier, "
          "legacy paid keys are tier 1, shortages debit nothing, replays, flag gate, 16×40 race")


async def race(dsn: str) -> None:
    """Pool of 16 connections, 40 mixed buys/opens on one player: limits and balances hold."""
    user = 993_000_000 + time.time_ns() % 1_000_000
    setup = await asyncpg.connect(dsn)
    sdb = PGAdapter(setup)
    flag_before = await system_flags.is_enabled(sdb, KEY_OFFERS_FLAG)
    try:
        await essence_repo.ensure_tables(sdb)
        await system_flags.set_flag(sdb, KEY_OFFERS_FLAG, True)
        await fund(sdb, user, mora=200_000, diamonds=200, zarniki=20_000, essence=5_000)
        pool = await asyncpg.create_pool(dsn, min_size=16, max_size=16)
        try:
            offers = list(KEY_OFFERS)

            async def task(index: int):
                async with pool.acquire() as conn:
                    db = PGAdapter(conn)
                    try:
                        if index % 3 == 2:
                            tier = (3, 4, 6)[index % 9 // 3]
                            return await chests_v1.prepare_free_open(
                                db, user_id=user, action_id=f"race-open-{index}", key_tier=tier, **cat())
                        return await chests_v1.buy_offer(db, user_id=user, offer_id=offers[index % len(offers)],
                                                         action_id=f"race-buy-{index}", **cat())
                    except chests_v1.ChestKeyConflict:
                        return None

            await asyncio.gather(*(task(index) for index in range(40)))
        finally:
            await pool.close()
        for offer_id, offer in KEY_OFFERS.items():
            column = "purchased_on" if offer["window"] == "day" else "purchased_week"
            async with sdb.execute(
                f"SELECT MAX(n) FROM (SELECT COUNT(*) n FROM chest_key_offer_purchases_v1 "
                f"WHERE user_id=? AND offer_id=? GROUP BY {column}) x", (user, offer_id),
            ) as cursor:
                most = (await cursor.fetchone())[0] or 0
            assert most <= offer["limit"], (offer_id, most)
        grants = await scalar(sdb, "SELECT COUNT(*) FROM chest_key_grants_v1 WHERE user_id=?", (user,))
        spends = await scalar(sdb, "SELECT COUNT(*) FROM chest_key_spends_v1 WHERE user_id=?", (user,))
        balance = await repo.get_balance(sdb, user)
        assert grants - spends == balance >= 0, (grants, spends, balance)
        assert sum((await repo.tier_balances(sdb, user)).values()) == balance
        mora, diamonds, zarniki, essence = await balances(sdb, user)
        assert min(mora, diamonds, zarniki, essence) >= 0
        async with sdb.execute(
            "SELECT p.offer_id,COUNT(*) FROM chest_key_offer_purchases_v1 p WHERE p.user_id=? GROUP BY 1", (user,),
        ) as cursor:
            bought = {row[0]: int(row[1]) for row in await cursor.fetchall()}
        assert bought == {o: int(offer["limit"]) for o, offer in KEY_OFFERS.items()}, bought
        spent_mora = sum(int(KEY_OFFERS[o]["price"].get("mora", 0)) * n for o, n in bought.items())
        assert mora == 200_000 - spent_mora, (mora, bought)
        async with sdb.execute(
            "SELECT o.stars,g.source_kind FROM chest_opens_v1 o JOIN chest_key_allocations_v1 a ON a.open_id=o.id "
            "JOIN chest_key_grants_v1 g ON g.id=a.grant_id WHERE o.user_id=?", (user,),
        ) as cursor:
            for stars, kind in await cursor.fetchall():
                tier = KEY_OFFERS[str(kind).removeprefix("offer_")]["tier"]
                assert int(stars) >= int(tier), (stars, kind)
    finally:
        await system_flags.set_flag(sdb, KEY_OFFERS_FLAG, flag_before)
        await setup.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
