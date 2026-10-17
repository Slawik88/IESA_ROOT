"""Real PostgreSQL race/rollback proof, unique disposable loopback-only schema."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.coin_market_v2 import MORA, MarketError
from core.economy_contract import IdempotencyConflict, InsufficientBalance
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import coin_market_v2 as repo
from infrastructure.repositories import economy_ledger, system_flags
from services import coin_market_v2 as service

DSN = "postgresql://predvestnik_preprod@127.0.0.1:55438/predvestnik_preprod"
SCHEMA = "cm2_test_" + uuid4().hex[:12]
os.environ["COIN_MARKET_V2_SECRET"] = (
    "test-only-coin-market-secret-with-no-production-value"
)


async def connect():
    conn = await asyncpg.connect(DSN)
    await conn.execute(f'SET search_path TO "{SCHEMA}"')
    return conn, PGAdapter(conn)


async def rejects(error, coro):
    try:
        await coro
    except error:
        return
    raise AssertionError(f"Expected {error.__name__}")


async def dust_regression(db, conn):
    created = await service.create_coin(db, 15, name="Dust fixture", zarniki=1000,
        deposit=1000 * MORA, action_id="dust_create_15")
    key = created["coin_id"]
    q = await service.quote(db, 16, key, "buy", amount=10 * MORA)
    await service.trade(db, 16, key, "buy", amount=10 * MORA,
        action_id="dust_buy_16", tick=q["tick"], price=service.money(q["price"]))
    units, _ = await repo.account(db, key, 16)
    q = await service.quote(db, 16, key, "sell", units=units - 1)
    await service.trade(db, 16, key, "sell", units=units - 1,
        action_id="dust_partial_16", tick=q["tick"], price=service.money(q["price"]))
    account_before = await repo.account(db, key, 16)
    assert account_before[0] == 1 and account_before[1] > 0
    q = await service.quote(db, 16, key, "sell", units=1)
    assert q["zero_payout"] and Decimal(q["received"]) == 0
    assert await repo.has_obligations(db, 16)
    balances = await repo.balances(db, 16)
    operations = await conn.fetchval("SELECT count(*) FROM economic_operations WHERE user_id=16")
    args = dict(units=1, action_id="dust_close_16", tick=q["tick"],
        price=service.money(q["price"]))
    with patch.object(repo, "receipt", side_effect=RuntimeError("fixture receipt failure")):
        await rejects(RuntimeError, service.trade(db, 16, key, "sell", **args))
    assert await repo.account(db, key, 16) == account_before
    assert await repo.balances(db, 16) == balances
    assert await repo.replay(db, 16, "dust_close_16") is None
    await system_flags.set_flag(db, "coin_market_v2", False)
    response = await service.trade(db, 16, key, "sell", **args)
    assert response["zero_payout"] and Decimal(response["received"]) == 0
    assert (await service.trade(db, 16, key, "sell", **args))["replayed"]
    assert await repo.account(db, key, 16) == (0, 0)
    assert not await repo.has_obligations(db, 16)
    assert await repo.balances(db, 16) == balances
    assert await conn.fetchval("SELECT count(*) FROM economic_operations WHERE user_id=16") == operations
    assert await conn.fetchval("SELECT count(*) FROM coin_market_v2_receipts WHERE user_id=16 AND action_id='dust_close_16' AND operation_id IS NULL") == 1
    assert await conn.fetchval("SELECT count(*) FROM coin_market_v2_events WHERE user_id=16 AND action_id='dust_close_16'") == 1
    row = await repo.load(db, key)
    _, book, _, _ = service.checked(row)
    await repo.reconcile(db, row, book)
    await system_flags.set_flag(db, "coin_market_v2", True)
    print("PASS: zero-payout quote, rollback, replay, unchanged wallet, zero cost and released obligation")


async def catalogue_regression(db, conn):
    # Disposable fixtures only: explicit reserves, no production funding operation.
    from core.coin_market_v2 import Book, Coin, PriceState

    tick = await repo.current_tick(db)
    _, secret_id = service.configuration()

    async def fixture(key, owner=None):
        coin = Coin(key, 20_000)
        await repo.insert_coin(db, coin=coin,
            book=Book(15_000 * MORA, insurance=1000 * MORA),
            state=PriceState(tick, coin.base), owner_id=owner,
            name=key, ticker=key, icon="coin", character="flow", group="test",
            rules=service.rules.RULES_VERSION, secret_id=secret_id)

    for i in range(499 - await repo.coin_count(db)):
        await fixture(f"cap_fixture_{i}")
    before = {uid: await repo.balances(db, uid) for uid in (17, 18)}

    async def create(uid):
        other, handle = await connect()
        try:
            return await service.create_coin(handle, uid,
                name=f"cap race {uid}", zarniki=1000, deposit=1000 * MORA,
                action_id=f"cap_creation_{uid}")
        finally:
            await other.close()

    answers = await asyncio.gather(create(17), create(18), return_exceptions=True)
    assert sum(isinstance(a, dict) for a in answers) == 1, answers
    assert sum(isinstance(a, MarketError) for a in answers) == 1, answers
    assert await repo.coin_count(db) == 500
    for uid, answer in zip((17, 18), answers):
        receipts = await conn.fetchval(
            "SELECT count(*) FROM coin_market_v2_receipts WHERE user_id=$1", uid)
        operations = await conn.fetchval(
            "SELECT count(*) FROM economic_operations WHERE user_id=$1", uid)
        assert receipts == operations == int(isinstance(answer, dict))
        if isinstance(answer, MarketError):
            assert "лимит" in str(answer), ascii(str(answer))
            assert await repo.balances(db, uid) == before[uid]

    # Simulate a historical overflow at the very end of the catalogue order.
    await fixture("overflow_tail", owner=20)
    assert await repo.coin_count(db) == 501
    q = await service.quote(db, 14, "overflow_tail", "short", amount=100 * MORA)
    opened = await service.trade(db, 14, "overflow_tail", "short",
        amount=100 * MORA, action_id="overflow_short", tick=q["tick"],
        price=service.money(q["price"]))
    await system_flags.set_flag(db, "coin_market_v2", False)
    market = await service.market(db, 14)
    assert len(market["coins"]) == 501
    assert any(p["id"] == opened["position_id"] for p in market["shorts"])
    assert (await service.availability(db, 20))["visible"]
    original_advance = service.advance
    old_tick = repo.decode((await repo.load(db, "overflow_tail"))["price_state"])["tick"]

    async def advance_tail(handle, coin_id):
        if coin_id == "overflow_tail":
            return await original_advance(handle, coin_id, target_tick=old_tick + 1)

    with patch.object(service, "advance", new=AsyncMock(side_effect=advance_tail)) as advance:
        await service.maintenance(db)
        visited = [call.args[1] for call in advance.call_args_list]
        assert len(visited) == 501 and "overflow_tail" in visited
    assert repo.decode((await repo.load(db, "overflow_tail"))["price_state"])["tick"] == old_tick + 1
    print("PASS: catalogue 499-way boundary, two-connection create race, rollback and historical overflow short/maintenance")


async def run():
    admin = await asyncpg.connect(DSN)
    await admin.execute(f'CREATE SCHEMA "{SCHEMA}"')
    conn = None
    try:
        conn, db = await connect()
        await conn.execute("""CREATE TABLE users(user_tg_id BIGINT PRIMARY KEY,
          user_balance_mora NUMERIC(24,6) DEFAULT 100000,user_balance_zarniki NUMERIC(24,6) DEFAULT 10000,
          user_balance_diamonds NUMERIC(24,6) DEFAULT 100,user_balance_dark_mora NUMERIC(24,6) DEFAULT 0,deleted_at TIMESTAMPTZ);
          CREATE TABLE user_reserve(user_id BIGINT PRIMARY KEY,reserved_mora NUMERIC(24,6) DEFAULT 0);
          CREATE TABLE wallet_log(id BIGSERIAL PRIMARY KEY,user_id BIGINT,chat_id BIGINT,target_id BIGINT,source TEXT,note TEXT,
          delta_mora NUMERIC(24,6),delta_zarniki NUMERIC(24,6),delta_diamonds NUMERIC(24,6),delta_dark_mora NUMERIC(24,6),
          balance_mora_after NUMERIC(24,6),balance_zarniki_after NUMERIC(24,6),balance_diamonds_after NUMERIC(24,6),balance_dark_mora_after NUMERIC(24,6),created_at TIMESTAMPTZ DEFAULT NOW());
          CREATE TABLE stars_payment_receipts_v1(user_id BIGINT,status TEXT);
          INSERT INTO users(user_tg_id) SELECT generate_series(1,20);""")
        await economy_ledger.ensure_tables(db)
        await system_flags.ensure_table(db)
        await repo.ensure_tables(db)
        await repo.ensure_tables(db)
        assert not await system_flags.is_enabled(db, "coin_market_v2")
        assert await service.bootstrap(db, source="explicit_test_funding")
        assert not await service.bootstrap(db, source="explicit_test_funding")
        assert await conn.fetchval("SELECT count(*) FROM coin_market_v2_coins") == 6
        await rejects(
            service.Unavailable, service.quote(db, 1, "orb", "buy", amount=10 * MORA)
        )
        await system_flags.set_flag(db, "coin_market_v2", True)
        await system_flags.set_flag(db, "coin_market_v2_shorts", True)
        q = await service.quote(db, 1, "orb", "buy", amount=100 * MORA)

        async def execute(uid=1, key="race_same_01", coin="orb", amount=100 * MORA):
            c, d = await connect()
            try:
                return await service.trade(
                    d,
                    uid,
                    coin,
                    "buy",
                    action_id=key,
                    tick=q["tick"],
                    price=service.money(q["price"]),
                    amount=amount,
                )
            finally:
                await c.close()

        responses = await asyncio.gather(*(execute() for _ in range(12)))
        assert sum(not r.get("replayed", False) for r in responses) == 1
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM economic_operations WHERE user_id=1"
            )
            == 1
        )
        await rejects(IdempotencyConflict, execute(amount=101 * MORA))
        units, cost = await repo.account(db, "orb", 1)
        assert cost == service.money(responses[0]["spent"])
        assert units > 0
        assert await repo.has_obligations(db, 1)
        await rejects(MarketError, service.quote(db, 2, "orb", "sell", units=units))
        await rejects(
            service.Requote,
            service.trade(
                db,
                1,
                "orb",
                "buy",
                action_id="stale_price_01",
                tick=q["tick"] - 1,
                price=service.money(q["price"]),
                amount=10 * MORA,
            ),
        )
        await conn.execute("UPDATE users SET user_balance_mora=0 WHERE user_tg_id=2")
        before = await repo.load(db, "orb")
        await rejects(InsufficientBalance, execute(uid=2, key="poor_wallet_01"))
        after = await repo.load(db, "orb")
        assert before["reserve"] == after["reserve"] and before["held"] == after["held"]

        # A fault AFTER the canonical wallet writer must roll back both legs.
        before_balance = await repo.balances(db, 1)

        async def fail(*_a, **_kw):
            raise RuntimeError("injected receipt failure")

        with patch.object(repo, "receipt", fail):
            await rejects(RuntimeError, execute(key="receipt_fault_01"))
        assert await repo.balances(db, 1) == before_balance
        assert await repo.replay(db, 1, "receipt_fault_01") is None

        await system_flags.set_flag(db, "coin_market_v2", False)
        assert (await execute())["replayed"]
        quote = await service.quote(db, 1, "orb", "sell", units=units)
        sold = await service.trade(
            db,
            1,
            "orb",
            "sell",
            units=units,
            action_id="sell_all_01",
            tick=quote["tick"],
            price=service.money(quote["price"]),
        )
        assert Decimal(sold["received"]) > 0
        assert await repo.account(db, "orb", 1) == (0, 0)
        assert not await repo.has_obligations(db, 1)
        await system_flags.set_flag(db, "coin_market_v2", True)
        await conn.execute("UPDATE users SET deleted_at=NOW() WHERE user_tg_id=9")
        await rejects(MarketError, execute(uid=9, key="deleted_user_01"))

        short_quote = await service.quote(db, 3, "veg", "short", amount=100 * MORA)
        opened = await service.trade(
            db,
            3,
            "veg",
            "short",
            amount=100 * MORA,
            action_id="short_open_01",
            tick=short_quote["tick"],
            price=service.money(short_quote["price"]),
        )
        pid = opened["position_id"]
        await rejects(
            MarketError, service.quote(db, 4, "veg", "close_short", position_id=pid)
        )
        cq = await service.quote(db, 3, "veg", "close_short", position_id=pid)

        async def close(key):
            c, d = await connect()
            try:
                return await service.trade(
                    d,
                    3,
                    "veg",
                    "close_short",
                    position_id=pid,
                    action_id=key,
                    tick=cq["tick"],
                    price=service.money(cq["price"]),
                )
            finally:
                await c.close()

        closed = await asyncio.gather(
            close("close_short_01"), close("close_short_02"), return_exceptions=True
        )
        assert sum(isinstance(r, dict) for r in closed) == 1
        assert sum(isinstance(r, MarketError) for r in closed) == 1

        created = await service.create_coin(
            db,
            5,
            name="Северная звезда",
            zarniki=2500,
            deposit=1000 * MORA,
            action_id="create_coin_01",
        )
        assert created["name"] == "Северная звезда"
        assert (
            await service.create_coin(
                db,
                5,
                name="Северная звезда",
                zarniki=2500,
                deposit=1000 * MORA,
                action_id="create_coin_01",
            )
        )["replayed"]
        await rejects(
            MarketError,
            service.create_coin(
                db,
                5,
                name="Другая монета",
                zarniki=1000,
                deposit=1000 * MORA,
                action_id="create_coin_02",
            ),
        )
        before_fund = int((await repo.lock_fund(db))["mora"])
        await service.create_coin(
            db,
            6,
            name="Лунная пыль",
            zarniki=1000,
            deposit=1000 * MORA,
            diamonds=True,
            action_id="create_gems_01",
        )
        assert int((await repo.lock_fund(db))["mora"]) == before_fund - 1000 * MORA
        assert Decimal((await repo.balances(db, 6))["diamonds"]) == 99
        assert Decimal((await repo.balances(db, 6))["mora"]) == 100000

        # Crash/restart state restoration: advance the same durable coin twice.
        row = await repo.load(db, "ine")
        target = json.loads(row["price_state"])["tick"] + 3
        await service.advance(db, "ine", target_tick=target)
        persisted = await repo.load(db, "ine")
        await service.advance(db, "ine", target_tick=target)
        assert persisted["price_state"] == (await repo.load(db, "ine"))["price_state"]
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM coin_market_v2_ticks WHERE coin_id='ine'"
            )
            == 4
        )

        # Liquidation after a lost maintenance window uses the pre-funded gap.
        oq = await service.quote(db, 7, "may", "short", amount=100 * MORA)
        await service.trade(
            db,
            7,
            "may",
            "short",
            amount=100 * MORA,
            action_id="auto_short_01",
            tick=oq["tick"],
            price=service.money(oq["price"]),
        )
        row = await repo.load(db, "may")
        coin, book, state, _ = service.checked(row)
        # A standard one-times position at base does not liquidate within +50%.
        # Set a permitted low entry for this independent stress coin, then short.
        await repo.save(db, "may", book, type(state)(state.tick, coin.floor))
        # Fixture transfers real treasury cash before accepting the low short.
        await conn.execute("UPDATE coin_market_v2_fund SET mora=mora-$1", 1000 * MORA)
        await repo.save(
            db,
            "may",
            replace(book, insurance=book.insurance + 1000 * MORA),
            type(state)(state.tick, coin.floor),
        )
        oq = await service.quote(db, 8, "may", "short", amount=100 * MORA)
        liquidated = await service.trade(
            db,
            8,
            "may",
            "short",
            amount=100 * MORA,
            action_id="low_short_01",
            tick=oq["tick"],
            price=service.money(oq["price"]),
        )
        row = await repo.load(db, "may")
        coin, book, state, _ = service.checked(row)
        await repo.save(db, "may", book, type(state)(state.tick, coin.ceiling))
        await service.advance(db, "may", target_tick=state.tick + 1)
        assert all(
            p["id"] != liquidated["position_id"]
            for p in await repo.active_shorts(db, "may")
        )
        assert Decimal((await repo.balances(db, 8))["mora"]) >= 99900

        for row in await repo.rows(db, 1):
            coin, book, _, _ = service.checked(row)
            await repo.reconcile(db, row, book)
            book.validate(coin)
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM coin_market_v2_events WHERE wallet+reserve+insurance+escrow+burned+treasury<>0"
            )
            == 0
        )
        try:
            await conn.execute("UPDATE coin_market_v2_receipts SET response='{}'")
        except asyncpg.RaiseError:
            pass
        else:
            raise AssertionError("receipts must be immutable")
        await dust_regression(db, conn)
        await catalogue_regression(db, conn)
        print(
            "PASS: real PostgreSQL bootstrap, 12-way replay, conflicts, stale quote, ownership, rollback, closed-entry exit, partial cash, short double-close, creation, treasury and restart"
        )
    finally:
        if conn:
            await conn.close()
        await admin.execute(f'DROP SCHEMA "{SCHEMA}" CASCADE')
        await admin.close()


if __name__ == "__main__":
    from decimal import Decimal

    asyncio.run(run())
