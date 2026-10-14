#!/usr/bin/env python3
"""Real PostgreSQL proof for ECO-04 PR-B shop: Polish, keys and exchange through one buy entry point."""
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

from core import shop_v1 as policy
from core.chests_v1 import KEY_OFFERS, KEY_OFFERS_FLAG
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import chests_v1 as chests_repo
from infrastructure.repositories import shop_v1 as repo
from infrastructure.repositories import skins_v3 as essence_repo
from infrastructure.repositories import system_flags
from infrastructure.repositories import zarniki_exchange_v1 as exchange_repo
from services import shop_v1 as shop


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


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


def cat() -> dict:
    return dict(catalog_version=policy.SHOP_VERSION, catalog_digest=policy.catalog_digest())


async def buy(db, user: int, item: str, action: str, amount: int | None = None) -> dict:
    return await shop.buy(db, user_id=user, item_id=item, action_id=action, amount=amount, **cat())


async def refused(coro, text: str = "", kind=shop.ShopConflict) -> str:
    try:
        await coro
    except kind as exc:
        assert text in str(exc), (text, str(exc))
        return str(exc)
    raise AssertionError(f"expected a refusal: {text}")


def by_id(view: dict) -> dict:
    return {item["id"]: item for section in view["sections"] for item in section["items"]}


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    tx = connection.transaction()
    await tx.start()
    real_window = repo.window
    try:
        db = PGAdapter(connection)
        await system_flags.ensure_table(db)
        await essence_repo.ensure_tables(db)
        await exchange_repo.ensure_tables(db)
        await repo.ensure_tables(db)
        await system_flags.set_flag(db, policy.FLAG, False)
        await system_flags.set_flag(db, KEY_OFFERS_FLAG, False)
        rich = 994_000_001
        await fund(db, rich, mora=100_000, diamonds=100, zarniki=1_000, essence=1_000)

        # Flag off: no screen, no purchase.
        await refused(shop.overview(db, user_id=rich), "Магазин пока закрыт", shop.ShopClosed)
        await refused(buy(db, rich, "ess_polish", "off-1"), "Магазин пока закрыт", shop.ShopClosed)
        await refused(shop.buy_polish(db, user_id=rich, action_id="off-2", requested_catalog_version=policy.SHOP_VERSION,
                                      requested_catalog_digest=policy.catalog_digest()), "закрыт", shop.ShopClosed)
        await system_flags.set_flag(db, policy.FLAG, True)

        # Keys stay unavailable until the tiered offers are on (pets_level_up_v1).
        view = await shop.overview(db, user_id=rich)
        items = by_id(view)
        assert view["keys_enabled"] is False and items["key_t4_zar"]["available"] is False
        assert items["key_t4_zar"]["unavailable_reason"] and [s["id"] for s in view["sections"]] == ["keys", "essence", "exchange"]
        assert {link["target"] for link in view["links"]} <= {"pass", "vip", "skins"} and "gifts" not in str(view["sections"])
        await refused(buy(db, rich, "key_t3_mora", "keys-off"), "недоступны")
        assert await scalar(db, "SELECT COUNT(*) FROM chest_key_offer_purchases_v1 WHERE user_id=?", (rich,)) == 0

        # Polish shortages: Mora only, 💎 only, both. Nothing is debited and every gap is named.
        cases = {994_000_011: (100, 5, {"mora": 500}), 994_000_012: (1_000, 0.5, {"diamonds": 1}),
                 994_000_013: (0, 0, {"mora": 600, "diamonds": 1})}
        for user, (mora, diamonds, gaps) in cases.items():
            await fund(db, user, mora=mora, diamonds=diamonds)
            before = await balances(db, user)
            message = await refused(buy(db, user, "ess_polish", f"poor-{user}"), "Не хватает")
            assert message == shop.missing_text(gaps), message
            assert ("🪙" in message) == ("mora" in gaps) and ("💎" in message) == ("diamonds" in gaps)
            assert await balances(db, user) == before
            assert await scalar(db, "SELECT COUNT(*) FROM shop_purchases_v1 WHERE user_id=?", (user,)) == 0
            assert await scalar(db, "SELECT COUNT(*) FROM economic_operations WHERE user_id=? AND reason_code=?",
                                (user, policy.POLISH_REASON_CODE)) == 0
            polish = by_id(await shop.overview(db, user_id=user))["ess_polish"]
            assert polish["missing"] == gaps and polish["affordable"] is False and polish["limit"]["left"] == 2

        # A fixed window drives the ISO-week limit across the UTC boundaries.
        monday, sunday = dt.date(2026, 10, 12), dt.date(2026, 10, 18)
        windows = {"now": (monday, monday, dt.datetime(2026, 10, 12, 0, 0, 1))}

        async def fixed_window(_db):
            return windows["now"]

        repo.window = fixed_window
        start = await balances(db, rich)
        first = await buy(db, rich, "ess_polish", "polish-1")
        receipt = first["receipt"]
        assert receipt["applied"] is True and receipt["price"] == {"mora": 600, "diamonds": 1}
        assert receipt["gives"] == {"essence": 60} and receipt["purchased_week"] == "2026-10-12"
        after = await balances(db, rich)
        assert (start[0] - after[0], start[1] - after[1], start[2] - after[2], after[3] - start[3]) == (600, 1, 0, 60)
        assert await scalar(db, "SELECT reason_code FROM economic_operations WHERE id=?",
                            (receipt["economy_operation_id"],)) == policy.POLISH_REASON_CODE
        assert await scalar(db, "SELECT COUNT(*) FROM skins_v3_essence_ledger WHERE user_id=? AND reason=? AND delta=60",
                            (rich, policy.POLISH_REASON_CODE)) == 1

        # Replay: same receipt, no second debit; another item with this action id is refused.
        replay = await buy(db, rich, "ess_polish", "polish-1")
        assert replay["receipt"] == {**receipt, "applied": False} and await balances(db, rich) == after
        stale = await shop.buy_polish(db, user_id=rich, action_id="polish-1", requested_catalog_version="old",
                                      requested_catalog_digest="stale")  # retry after a deploy changed the catalogue
        assert stale == {**receipt, "applied": False} and await balances(db, rich) == after
        await system_flags.set_flag(db, KEY_OFFERS_FLAG, True)
        await refused(buy(db, rich, "key_t3_mora", "polish-1"), "action_id")
        await refused(buy(db, rich, "exchange_mora", "polish-1", amount=1), "action_id")
        await refused(buy(db, rich, "gift_rose", "gift-1"), "нет")
        await refused(shop.buy(db, user_id=rich, item_id="ess_polish", action_id="stale", catalog_version=policy.SHOP_VERSION,
                               catalog_digest="0" * 64), "Каталог")

        # Two per week; the third is refused; Sunday is the same week; next Monday resets.
        assert (await buy(db, rich, "ess_polish", "polish-2"))["receipt"]["applied"]
        await refused(buy(db, rich, "ess_polish", "polish-3"), "Лимит на этой неделе")
        polish = by_id(await shop.overview(db, user_id=rich))["ess_polish"]
        assert polish["limit"]["used"] == 2 and polish["limit"]["left"] == 0 and polish["available"] is False
        assert polish["affordable"] is True and polish["limit"]["resets_in_seconds"] == 7 * 86400 - 1
        windows["now"] = (sunday, monday, dt.datetime(2026, 10, 18, 23, 59, 59))
        await refused(buy(db, rich, "ess_polish", "polish-sun"), "Лимит")
        assert by_id(await shop.overview(db, user_id=rich))["ess_polish"]["limit"]["resets_in_seconds"] == 1
        windows["now"] = (sunday + dt.timedelta(days=1), sunday + dt.timedelta(days=1), dt.datetime(2026, 10, 19, 0, 0))
        assert (await buy(db, rich, "ess_polish", "polish-next"))["receipt"]["purchased_week"] == "2026-10-19"
        assert await scalar(db, "SELECT COUNT(*) FROM shop_purchases_v1 WHERE user_id=?", (rich,)) == 3
        repo.window = real_window

        # Flag off again: new purchases are refused, a replay still returns its receipt.
        await system_flags.set_flag(db, policy.FLAG, False)
        await refused(buy(db, rich, "ess_polish", "polish-off"), "закрыт", shop.ShopClosed)
        assert (await buy(db, rich, "ess_polish", "polish-1"))["receipt"]["purchase_id"] == receipt["purchase_id"]
        await system_flags.set_flag(db, policy.FLAG, True)

        # Keys through the shop: the chest offer receipt and a key of the right tier, same limits.
        tiers_before = await chests_repo.tier_balances(db, rich)
        bought = await buy(db, rich, "key_t6_dia", "key-plat-1")
        assert bought["receipt"]["offer_id"] == "platinum_diamonds" and bought["receipt"]["key_tier"] == 6
        row = await chests_repo.find_offer_purchase(db, user_id=rich, action_id="key-plat-1")
        assert row and row["offer_id"] == "platinum_diamonds" and int(row["key_tier"]) == 6
        tiers_after = await chests_repo.tier_balances(db, rich)
        assert tiers_after[6] == tiers_before[6] + 1 and bought["balances"]["diamonds"] == after[1] - 2 - 5
        assert (await buy(db, rich, "key_t6_dia", "key-plat-1"))["receipt"]["applied"] is False
        await refused(buy(db, rich, "key_t3_mora", "key-plat-1"), "action_id")  # same action, other key: chest replay check
        await refused(buy(db, rich, "ess_polish", "key-plat-1"), "action_id")
        await refused(buy(db, rich, "key_t6_dia", "key-plat-2"), "Лимит")
        view = await shop.overview(db, user_id=rich)
        plat = by_id(view)["key_t6_dia"]
        assert plat["limit"]["left"] == 0 and plat["available"] is False and plat["odds"] == {"stars": 6, "percent": 97.0}
        assert view["balances"]["keys"]["6"] == tiers_after[6] and {o["percent"] for o in view["key_odds"]} == {89.0, 97.0}
        craft = by_id(view)["key_t4_craft"]
        assert craft["cost"] == KEY_OFFERS["silver_craft"]["price"] and craft["mode"] == "craft" and craft["limit"]["left"] == 1

        # Exchange through the shop: the shared 50 ✨ daily cap holds; the action id is the idempotency key.
        trader = 994_000_021
        await fund(db, trader, mora=0, diamonds=0, zarniki=200)
        first_ex = await buy(db, trader, "exchange_mora", "ex-1", amount=30)
        assert first_ex["receipt"]["zarniki_spent"] == 30 and first_ex["balances"]["mora"] == 300
        assert (await buy(db, trader, "exchange_mora", "ex-1", amount=30))["receipt"]["idempotent_replay"] is True
        await refused(buy(db, trader, "exchange_mora", "ex-1", amount=31), "action_id")
        await refused(buy(db, trader, "exchange_dia", "ex-2", amount=21), "осталось 20")
        assert (await buy(db, trader, "exchange_dia", "ex-2", amount=20))["balances"]["diamonds"] == 0.2
        await refused(buy(db, trader, "exchange_mora", "ex-3", amount=1), "осталось 0")
        await refused(buy(db, trader, "exchange_mora", "ex-4"), "Сумма обмена")
        await refused(buy(db, trader, "ess_polish", "ex-5", amount=2), "по одному")
        ex = by_id(await shop.overview(db, user_id=trader))
        assert ex["exchange_mora"]["limit"]["left"] == 0 and ex["exchange_dia"]["limit"]["used"] == 50
        assert ex["exchange_mora"]["max_amount"] == 0 and ex["exchange_mora"]["available"] is False
        assert (await balances(db, trader))[2] == 150

        # /me: left, missing and affordable per currency for a player who can pay for some things only.
        mid = 994_000_031
        await fund(db, mid, mora=700, diamonds=0.4, zarniki=130, essence=150)
        view = await shop.overview(db, user_id=mid)
        items = by_id(view)
        assert view["balances"]["mora"] == 700 and view["balances"]["essence"] == 150 and view["balances"]["diamonds"] == 0.4
        assert items["ess_polish"]["missing"] == {"diamonds": 1} and items["ess_polish"]["affordable"] is False
        assert items["key_t4_zar"]["missing"] == {} and items["key_t4_zar"]["affordable"] is True
        assert items["key_t4_zar"]["limit"] | {"resets_in_seconds": 0} == {
            "period": "day", "max": 2, "unit": "keys", "used": 0, "left": 2, "resets_in_seconds": 0}
        assert items["key_t4_craft"]["missing"] == {"essence": 50} and items["key_t3_mora"]["missing"] == {"mora": 100}
        assert items["key_t6_zar"]["missing"] == {"zarniki": 170}
        assert items["key_t6_dia"]["missing"] == {"diamonds": 5, "mora": 2300}
        assert items["exchange_mora"]["max_amount"] == 50 and items["exchange_mora"]["affordable"] is True
        assert 0 < items["key_t4_zar"]["limit"]["resets_in_seconds"] <= 86400
        assert all(item["available"] for item in items.values())
        assert "dark_mora" not in view["balances"] and "echo" not in str(view).lower()
    finally:
        repo.window = real_window
        await tx.rollback()
        await connection.close()

    await race(dsn)
    print("OK: shop — Polish shortages debit nothing and name each currency, replay = same receipt, action id bound to "
          "one item, 2/week on the UTC ISO week, flag gate, keys = chest offer receipts, exchange 50 ✨ cap, /me states, 16×30 race")


async def race(dsn: str) -> None:
    """Pool of 16 connections, 30 Polish buys on one player: never more than two a week."""
    user = 995_000_000 + time.time_ns() % 1_000_000
    setup = await asyncpg.connect(dsn)
    sdb = PGAdapter(setup)
    await system_flags.ensure_table(sdb)
    flag_before = await system_flags.is_enabled(sdb, policy.FLAG)
    try:
        await essence_repo.ensure_tables(sdb)
        await exchange_repo.ensure_tables(sdb)
        await repo.ensure_tables(sdb)
        await system_flags.set_flag(sdb, policy.FLAG, True)
        await fund(sdb, user, mora=100_000, diamonds=100)
        pool = await asyncpg.create_pool(dsn, min_size=16, max_size=16)
        try:
            async def task(index: int):
                async with pool.acquire() as conn:
                    db = PGAdapter(conn)
                    try:
                        return await buy(db, user, "ess_polish", f"race-polish-{index % 25}")
                    except shop.ShopConflict:
                        return None

            results = await asyncio.gather(*(task(index) for index in range(30)))
        finally:
            await pool.close()
        applied = [r for r in results if r and r["receipt"]["applied"]]
        assert len(applied) == 2, len(applied)
        async with sdb.execute(
            "SELECT MAX(n) FROM (SELECT COUNT(*) n FROM shop_purchases_v1 WHERE user_id=? GROUP BY purchased_week) x",
            (user,),
        ) as cursor:
            assert (await cursor.fetchone())[0] == 2
        mora, diamonds, _zarniki, essence = await balances(sdb, user)
        assert (mora, diamonds, essence) == (100_000 - 1_200, 98, 120), (mora, diamonds, essence)
        assert await scalar(sdb, "SELECT COUNT(*) FROM economic_operations WHERE user_id=? AND reason_code=?",
                            (user, policy.POLISH_REASON_CODE)) == 2
    finally:
        await system_flags.set_flag(sdb, policy.FLAG, flag_before)
        await setup.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
