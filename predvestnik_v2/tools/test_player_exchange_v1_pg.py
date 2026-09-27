#!/usr/bin/env python3
"""Loopback PostgreSQL proof for atomic player-coin creation."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
from urllib.parse import urlparse

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.economy_contract import IdempotencyConflict, InsufficientBalance
from core.player_exchange_v1 import PlayerExchangePolicyError
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import economy_ledger, player_exchange_v1 as repo, system_flags
from services import player_exchange_v1 as service

SCHEMA = "player_exchange_v1_contract"


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def connect(dsn: str):
    conn = await asyncpg.connect(dsn)
    await conn.execute(f'SET search_path TO "{SCHEMA}"')
    return conn, PGAdapter(conn)


async def prepare(dsn: str):
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
        await conn.execute(f'CREATE SCHEMA "{SCHEMA}"')
        await conn.execute(f'SET search_path TO "{SCHEMA}"')
        await conn.execute("""
            CREATE TABLE users (
                user_tg_id BIGINT PRIMARY KEY,
                user_balance_mora NUMERIC(24,6) NOT NULL DEFAULT 0,
                user_balance_diamonds NUMERIC(24,6) NOT NULL DEFAULT 0,
                user_balance_dark_mora NUMERIC(24,6) NOT NULL DEFAULT 0,
                user_balance_zarniki NUMERIC(24,6) NOT NULL DEFAULT 0
            );
            CREATE TABLE wallet_log (
                id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL,chat_id BIGINT,
                delta_mora NUMERIC(24,6) NOT NULL DEFAULT 0,delta_diamonds NUMERIC(24,6) NOT NULL DEFAULT 0,
                delta_dark_mora NUMERIC(24,6) NOT NULL DEFAULT 0,delta_zarniki NUMERIC(24,6) NOT NULL DEFAULT 0,
                balance_mora_after NUMERIC(24,6) NOT NULL DEFAULT 0,balance_diamonds_after NUMERIC(24,6) NOT NULL DEFAULT 0,
                balance_dark_mora_after NUMERIC(24,6) NOT NULL DEFAULT 0,balance_zarniki_after NUMERIC(24,6) NOT NULL DEFAULT 0,
                source TEXT NOT NULL,target_id BIGINT,note TEXT,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE user_reserve (user_id BIGINT PRIMARY KEY,reserved_mora NUMERIC(24,6) NOT NULL DEFAULT 0)
        """)
        await conn.execute("""
            CREATE TABLE user_login_signals (
                user_id BIGINT NOT NULL,kind TEXT NOT NULL,value_hash TEXT NOT NULL,
                first_seen TIMESTAMP NOT NULL DEFAULT NOW(),last_seen TIMESTAMP NOT NULL DEFAULT NOW(),
                hits INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(user_id,kind,value_hash)
            )
        """)
        db = PGAdapter(conn)
        await economy_ledger.ensure_tables(db)
        await system_flags.ensure_table(db)
        await repo.ensure_tables(db)
        assert await repo.schema_ready(db) is True
        await db.execute("DELETE FROM player_exchange_schema_v1")
        await db.commit()
        assert await repo.schema_ready(db) is False
        await repo.ensure_tables(db)
        await db.execute("UPDATE system_flags SET enabled=1 WHERE key=?", (service.FEATURE_FLAG_KEY,))
        await db.execute(
            "INSERT INTO users(user_tg_id,user_balance_mora,user_balance_zarniki) VALUES "
            "(1,100000,10000),(2,100000,10000),(3,100,100),(4,100000,10000),"
            "(5,100000,10000),(6,100000,10000),(7,100000,10000),"
            "(8,100000,10000),(9,100000,10000),(10,100000,10000),"
            "(11,100000,10000),(12,100000,10000)"
        )
        await db.commit()
    finally:
        await conn.close()


async def create(dsn: str, user: int, name: str, ticker: str, action: str):
    conn, db = await connect(dsn)
    try:
        return await service.create_coin(db, owner_id=user, name=name, ticker=ticker, initial_mora=10000, action_id=action)
    finally:
        await conn.close()


async def settle(dsn: str, coin_id: str):
    conn, db = await connect(dsn)
    try:
        return await service.settle_auction(db, coin_id=coin_id)
    finally:
        await conn.close()


async def main(dsn: str):
    await prepare(dsn)
    first = await create(dsn, 1, "Северная звезда", "STAR", "create-action-0001")
    replay = await create(dsn, 1, "Северная звезда", "STAR", "create-action-0001")
    assert first["id"] == replay["id"] and replay["replayed"] is True
    try:
        await create(dsn, 1, "Другая монета", "OTHER", "create-action-0001")
        raise AssertionError("changed replay was accepted")
    except IdempotencyConflict:
        pass

    results = await asyncio.gather(
        create(dsn, 2, "Лунный свет", "MOON", "create-action-0002"),
        create(dsn, 2, "Солнечный свет", "SUN", "create-action-0003"),
        return_exceptions=True,
    )
    assert sum(not isinstance(item, Exception) for item in results) == 1

    same = await asyncio.gather(
        create(dsn, 5, "Одна операция", "ONCE", "create-action-0005"),
        create(dsn, 5, "Одна операция", "ONCE", "create-action-0005"),
    )
    assert same[0]["id"] == same[1]["id"]

    try:
        await create(dsn, 3, "Бедная монета", "POOR", "create-action-0006")
        raise AssertionError("insufficient balance was accepted")
    except InsufficientBalance:
        pass

    conn, db = await connect(dsn)
    try:
        await db.execute("UPDATE player_coins_v1 SET status='archived' WHERE id=?", (first["id"],))
        await db.commit()
    finally:
        await conn.close()
    try:
        await create(dsn, 4, "Северная звезда", "STAR", "create-action-0007")
        raise AssertionError("archived identifiers were reused")
    except PlayerExchangePolicyError:
        pass

    conn, db = await connect(dsn)
    try:
        await db.execute("UPDATE system_flags SET enabled=0 WHERE key=?", (service.FEATURE_FLAG_KEY,))
        await db.commit()
    finally:
        await conn.close()
    try:
        await create(dsn, 6, "Закрытый рынок", "CLOSE", "create-action-0008")
        raise AssertionError("disabled exchange accepted creation")
    except service.PlayerExchangeUnavailable:
        pass

    conn, db = await connect(dsn)
    try:
        await db.execute("UPDATE system_flags SET enabled=1 WHERE key=?", (service.FEATURE_FLAG_KEY,))
        await db.commit()
        launched = await service.create_coin(
            db, owner_id=7, name="Рыночная монета", ticker="MARKT",
            initial_mora=10000, action_id="create-action-0009",
        )
        await service.place_auction_bid(
            db, bidder_id=8, coin_id=launched["id"], max_price_mora="1",
            escrow_mora=20000, action_id="bid-action-0001",
        )
        await service.place_auction_bid(
            db, bidder_id=9, coin_id=launched["id"], max_price_mora="1",
            escrow_mora=20000, action_id="bid-action-0002",
        )
        try:
            await service.place_auction_bid(
                db, bidder_id=8, coin_id=launched["id"], max_price_mora="2",
                escrow_mora=100, action_id="bid-action-second",
            )
            raise AssertionError("second bid was accepted")
        except PlayerExchangePolicyError:
            pass
        try:
            await service.place_auction_bid(
                db, bidder_id=11, coin_id=launched["id"], max_price_mora="Infinity",
                escrow_mora=100, action_id="bid-action-infinite",
            )
            raise AssertionError("non-finite price was accepted")
        except PlayerExchangePolicyError:
            pass
        await db.execute(
            "INSERT INTO user_login_signals(user_id,kind,value_hash,hits) VALUES "
            "(7,'ip','same-ip',2),(11,'ip','same-ip',2),"
            "(7,'fp','same-fp',2),(12,'ip','same-ip',2),(12,'fp','same-fp',2)"
        )
        assert await repo.bidder_has_shared_owner_signal(db, bidder_id=11, owner_id=7) is False
        assert await repo.bidder_has_shared_owner_signal(db, bidder_id=12, owner_id=7) is True
        await db.execute(
            "UPDATE player_coins_v1 SET auction_starts_at=NOW()-INTERVAL '2 hours',"
            "auction_ends_at=NOW()-INTERVAL '1 second' WHERE id=?", (launched["id"],)
        )
        await db.commit()
        concurrent_settlements = await asyncio.gather(
            settle(dsn, launched["id"]), settle(dsn, launched["id"]),
        )
        settled = next(item for item in concurrent_settlements if not item["replayed"])
        replayed_settlement = next(item for item in concurrent_settlements if item["replayed"])
        assert settled["success"] is True and replayed_settlement["replayed"] is True
        assert int(settled["sold_units"]) == 40_000_000
        ladder_rows = await conn.fetch(
            "SELECT * FROM player_coin_orders_v1 WHERE coin_id=$1 AND actor_kind='treasury' ORDER BY side,limit_price_micromora",
            launched["id"],
        )
        assert len(ladder_rows) == 10
        assert sum(1 for row in ladder_rows if row["side"] == "buy") == 5
        assert sum(1 for row in ladder_rows if row["side"] == "sell") == 5
        treasury_free = await conn.fetchval(
            "SELECT treasury_mora FROM player_coin_mora_accounts_v1 WHERE coin_id=$1", launched["id"],
        )
        treasury_reserved = sum(row["reserved_mora"] for row in ladder_rows)
        assert float(treasury_free + treasury_reserved) == 50000
        assert sum(int(row["remaining_units"]) for row in ladder_rows if row["side"] == "sell") == 300_000_000
        public_ladder = await repo.public_order_book(db, launched["id"])
        assert sum(int(row["treasury_units"]) for row in public_ladder["asks"]) == 300_000_000
        launch_stats = (await service.public_market(db, coin_id=launched["id"]))["stats_24h"]
        assert launch_stats["vwap_5m_price_micromora"] is None
        assert launch_stats["reference_price_micromora"] == 1_000_000
        assert launch_stats["market_cap_mora"] == 40_000
        assert launch_stats["best_bid_micromora"] == 980_000
        assert launch_stats["best_ask_micromora"] == 1_020_000
        assert launch_stats["spread_micromora"] == 40_000
        assert launch_stats["spread_percent"] == 4
        owner_cross = await service.place_limit_order(
            db, user_id=7, coin_id=launched["id"], side="buy", amount="10",
            limit_price_mora="2", time_in_force="gtc", action_id="order-owner-cross01",
        )
        assert await service.match_market(db, coin_id=launched["id"]) == []
        assert (await repo.get_order(db, owner_cross["id"]))["status"] == "cancelled"
        circulation_before = await conn.fetchval(
            "SELECT circulating_units FROM player_coins_v1 WHERE id=$1", launched["id"],
        )
        treasury_before_trade = await conn.fetchval(
            "SELECT treasury_mora FROM player_coin_mora_accounts_v1 WHERE coin_id=$1", launched["id"],
        )
        await service.place_limit_order(
            db, user_id=12, coin_id=launched["id"], side="buy", amount="10",
            limit_price_mora="2", time_in_force="gtc", action_id="order-treasury-buy1",
        )
        treasury_trades = await service.match_market(db, coin_id=launched["id"])
        assert len(treasury_trades) == 1
        assert await conn.fetchval(
            "SELECT seller_kind FROM player_coin_trades_v1 WHERE id=$1", treasury_trades[0]["trade_id"],
        ) == "treasury"
        assert await conn.fetchval(
            "SELECT treasury_mora FROM player_coin_mora_accounts_v1 WHERE coin_id=$1", launched["id"],
        ) > treasury_before_trade
        assert await conn.fetchval(
            "SELECT circulating_units FROM player_coins_v1 WHERE id=$1", launched["id"],
        ) == circulation_before + 10_000
        await service.place_limit_order(
            db, user_id=8, coin_id=launched["id"], side="sell", amount="20",
            limit_price_mora="0.5", time_in_force="gtc", action_id="order-treasury-sell1",
        )
        treasury_buy_trades = await service.match_market(db, coin_id=launched["id"])
        assert len(treasury_buy_trades) == 1
        assert await conn.fetchval(
            "SELECT buyer_kind FROM player_coin_trades_v1 WHERE id=$1", treasury_buy_trades[0]["trade_id"],
        ) == "treasury"
        assert await conn.fetchval(
            "SELECT circulating_units FROM player_coins_v1 WHERE id=$1", launched["id"],
        ) == circulation_before - 10_000
        live_stats = (await service.public_market(db, coin_id=launched["id"]))["stats_24h"]
        assert live_stats["best_bid_micromora"] is not None and live_stats["best_ask_micromora"] is not None
        assert live_stats["spread_micromora"] == live_stats["best_ask_micromora"] - live_stats["best_bid_micromora"]
        assert live_stats["vwap_5m_price_micromora"] is not None
        assert live_stats["volume_5m_mora"] > 0
        assert live_stats["depth_5pct"]["total_mora"] > 0
        assert live_stats["market_cap_mora"] > 0
        ladder_rows = await conn.fetch(
            "SELECT * FROM player_coin_orders_v1 WHERE coin_id=$1 AND actor_kind='treasury' AND status='open'",
            launched["id"],
        )
        for row in ladder_rows:
            try:
                await service.cancel_order(db, user_id=7, order_id=str(row["id"]))
                raise AssertionError("owner cancelled a treasury order through the player endpoint")
            except PlayerExchangePolicyError:
                pass
            await service._release_order(db, dict(row), reason="contract_cleanup")
        assert float(await conn.fetchval(
            "SELECT treasury_mora FROM player_coin_mora_accounts_v1 WHERE coin_id=$1", launched["id"],
        )) == 49988.6
        assert await conn.fetchval("SELECT COUNT(*) FROM economic_operations WHERE user_id=8") == 2
        assert await conn.fetchval(
            "SELECT COUNT(*) FROM player_coin_events_v1 WHERE coin_id=$1 AND event_type IN ('auction_bid_placed','auction_bid_settled')",
            launched["id"],
        ) == 4

        sell_order = await service.place_limit_order(
            db, user_id=8, coin_id=launched["id"], side="sell", amount="10",
            limit_price_mora="2", time_in_force="gtc", action_id="order-sell-0001",
        )
        buy_order = await service.place_limit_order(
            db, user_id=9, coin_id=launched["id"], side="buy", amount="10",
            limit_price_mora="2", time_in_force="gtc", action_id="order-buy-0001",
        )
        trades = await service.match_market(db, coin_id=launched["id"])
        assert len(trades) == 1 and trades[0]["units"] == 10_000
        sell_final = await repo.get_order(db, sell_order["id"])
        buy_final = await repo.get_order(db, buy_order["id"])
        assert sell_final["status"] == "filled" and buy_final["status"] == "filled"
        assert float(buy_final["reserved_mora"]) == 0
        assert await conn.fetchval("SELECT COUNT(*) FROM player_coin_trades_v1 WHERE coin_id=$1", launched["id"]) == 3
        fee_fund = await conn.fetchrow(
            "SELECT insurance_mora,burned_mora FROM player_exchange_fee_fund_v1 WHERE singleton=TRUE"
        )
        assert float(fee_fund[0]) == 1.8 and float(fee_fund[1]) == 4.2
        trader8 = await conn.fetchrow("SELECT user_balance_mora FROM users WHERE user_tg_id=8")
        trader9 = await conn.fetchrow("SELECT user_balance_mora FROM users WHERE user_tg_id=9")
        assert float(trader8[0]) == 80037.6 and float(trader9[0]) == 79979
        token8 = await repo.get_player_coin_account(db, coin_id=launched["id"], user_id=8)
        token9 = await repo.get_player_coin_account(db, coin_id=launched["id"], user_id=9)
        assert int(token8["available_units"]) == 19_970_000 and int(token8["reserved_units"]) == 0
        assert int(token9["available_units"]) == 20_010_000 and int(token9["reserved_units"]) == 0
        try:
            await conn.execute("DELETE FROM player_coin_trades_v1 WHERE coin_id=$1", launched["id"])
            raise AssertionError("append-only trade was mutable")
        except asyncpg.RaiseError:
            pass
        cancellable = await service.place_limit_order(
            db, user_id=11, coin_id=launched["id"], side="buy", amount="10",
            limit_price_mora="1", time_in_force="gtc", action_id="order-cancel-0001",
        )
        cancelled = await service.cancel_order(db, user_id=11, order_id=cancellable["id"])
        assert cancelled["status"] == "cancelled"
        assert float(await conn.fetchval("SELECT user_balance_mora FROM users WHERE user_tg_id=11")) == 100000
        try:
            await service.place_limit_order(
                db, user_id=11, coin_id=launched["id"], side="buy", amount="0.001",
                limit_price_mora="0.000001", time_in_force="gtc", action_id="order-dust-00001",
            )
            raise AssertionError("dust order was accepted")
        except PlayerExchangePolicyError:
            pass

        self_sell = await service.place_limit_order(
            db, user_id=8, coin_id=launched["id"], side="sell", amount="10",
            limit_price_mora="1", time_in_force="gtc", action_id="order-self-sell",
        )
        self_buy = await service.place_limit_order(
            db, user_id=8, coin_id=launched["id"], side="buy", amount="10",
            limit_price_mora="1", time_in_force="gtc", action_id="order-self-buy-1",
        )
        assert await service.match_market(db, coin_id=launched["id"]) == []
        assert (await repo.get_order(db, self_buy["id"]))["status"] == "cancelled"
        assert (await repo.get_order(db, self_sell["id"]))["status"] == "open"
        await service.cancel_order(db, user_id=8, order_id=self_sell["id"])
        token8_after = await repo.get_player_coin_account(db, coin_id=launched["id"], user_id=8)
        assert int(token8_after["available_units"]) == 19_970_000
        await service.place_limit_order(
            db, user_id=8, coin_id=launched["id"], side="sell", amount="5",
            limit_price_mora="2", time_in_force="gtc", action_id="order-part-sell1",
        )
        await service.place_limit_order(
            db, user_id=8, coin_id=launched["id"], side="sell", amount="5",
            limit_price_mora="2", time_in_force="gtc", action_id="order-part-sell2",
        )
        partial_buy = await service.place_limit_order(
            db, user_id=9, coin_id=launched["id"], side="buy", amount="10",
            limit_price_mora="2", time_in_force="gtc", action_id="order-part-buy01",
        )
        partial_trades = await service.match_market(db, coin_id=launched["id"])
        assert len(partial_trades) == 2
        assert (await repo.get_order(db, partial_buy["id"]))["reserved_mora"] == 0
        ioc_seller_mora_before = float(await conn.fetchval("SELECT user_balance_mora FROM users WHERE user_tg_id=8"))
        ioc_buyer_mora_before = float(await conn.fetchval("SELECT user_balance_mora FROM users WHERE user_tg_id=9"))
        ioc_seller_tokens_before = int((await repo.get_player_coin_account(db, coin_id=launched["id"], user_id=8))["available_units"])
        ioc_buyer_tokens_before = int((await repo.get_player_coin_account(db, coin_id=launched["id"], user_id=9))["available_units"])
        await service.place_limit_order(
            db, user_id=8, coin_id=launched["id"], side="sell", amount="10",
            limit_price_mora="2", time_in_force="gtc", action_id="order-ioc-sell001",
        )
        ioc = await service.place_protected_market_order(
            db, user_id=9, coin_id=launched["id"], side="buy", amount="20",
            slippage_percent=3, action_id="order-ioc-buy0001",
        )
        assert ioc["time_in_force"] == "ioc" and ioc["status"] == "cancelled"
        assert int(ioc["original_units"]) == 20_000 and int(ioc["remaining_units"]) == 0
        assert float(ioc["reserved_mora"]) == 0
        ioc_replay = await service.place_protected_market_order(
            db, user_id=9, coin_id=launched["id"], side="buy", amount="20",
            slippage_percent=3, action_id="order-ioc-buy0001",
        )
        assert ioc_replay["id"] == ioc["id"] and ioc_replay["replayed"] is True
        assert float(await conn.fetchval("SELECT user_balance_mora FROM users WHERE user_tg_id=8")) == ioc_seller_mora_before + 19
        assert float(await conn.fetchval("SELECT user_balance_mora FROM users WHERE user_tg_id=9")) == ioc_buyer_mora_before - 21
        ioc_seller_tokens_after = await repo.get_player_coin_account(db, coin_id=launched["id"], user_id=8)
        ioc_buyer_tokens_after = await repo.get_player_coin_account(db, coin_id=launched["id"], user_id=9)
        assert int(ioc_seller_tokens_after["available_units"]) == ioc_seller_tokens_before - 10_000
        assert int(ioc_buyer_tokens_after["available_units"]) == ioc_buyer_tokens_before + 10_000
        dust_sell = await service.place_limit_order(
            db, user_id=9, coin_id=launched["id"], side="sell", amount="20000",
            limit_price_mora="0.0005", time_in_force="gtc", action_id="order-cross-dust-s",
        )
        dust_buy = await service.place_limit_order(
            db, user_id=8, coin_id=launched["id"], side="buy", amount="0.001",
            limit_price_mora="10000", time_in_force="gtc", action_id="order-cross-dust-b",
        )
        assert await service.match_market(db, coin_id=launched["id"]) == []
        assert (await repo.get_order(db, dust_buy["id"]))["status"] == "cancelled"
        assert (await repo.get_order(db, dust_sell["id"]))["status"] == "open"
        await service.cancel_order(db, user_id=9, order_id=dust_sell["id"])
        disabled_sell = await service.place_limit_order(
            db, user_id=8, coin_id=launched["id"], side="sell", amount="10",
            limit_price_mora="2", time_in_force="gtc", action_id="order-disabled-sell",
        )
        disabled_buy = await service.place_limit_order(
            db, user_id=9, coin_id=launched["id"], side="buy", amount="10",
            limit_price_mora="2", time_in_force="gtc", action_id="order-disabled-buy1",
        )
        await db.execute("UPDATE system_flags SET enabled=0 WHERE key=?", (service.FEATURE_FLAG_KEY,))
        await db.commit()
        assert await service.match_market(db, coin_id=launched["id"]) == []
        assert (await repo.get_order(db, disabled_sell["id"]))["status"] == "open"
        assert (await repo.get_order(db, disabled_buy["id"]))["status"] == "open"
        assert (await service.cancel_order(db, user_id=8, order_id=disabled_sell["id"]))["status"] == "cancelled"
        assert (await service.cancel_order(db, user_id=9, order_id=disabled_buy["id"]))["status"] == "cancelled"
        await db.execute("UPDATE system_flags SET enabled=1 WHERE key=?", (service.FEATURE_FLAG_KEY,))
        await db.commit()
        for suffix, age in (("5m", 7), ("1h", 70)):
            baseline_price = 1_000_000 if suffix == "5m" else 2_000_000
            baseline_gross = 100 if suffix == "5m" else 200
            await conn.execute(
                "INSERT INTO player_coin_trades_v1"
                "(id,coin_id,buy_order_id,sell_order_id,buyer_id,seller_id,units,price_micromora,"
                "gross_mora,buyer_fee_mora,seller_fee_mora,created_at) "
                "VALUES($1,$2,$3,$4,9,8,100000,$5,$6,0,0,NOW()-($7::integer*INTERVAL '1 minute'))",
                f"baseline-{suffix}", launched["id"], partial_buy["id"], sell_order["id"],
                baseline_price, baseline_gross, age,
            )
        await service.place_limit_order(
            db, user_id=8, coin_id=launched["id"], side="sell", amount="5",
            limit_price_mora="3", time_in_force="gtc", action_id="order-halt-sell01",
        )
        await service.place_limit_order(
            db, user_id=9, coin_id=launched["id"], side="buy", amount="5",
            limit_price_mora="3", time_in_force="gtc", action_id="order-halt-buy001",
        )
        assert len(await service.match_market(db, coin_id=launched["id"])) == 1
        await db.execute("DELETE FROM player_coin_market_state_v1 WHERE coin_id=?", (launched["id"],))
        await db.commit()
        await service.place_limit_order(
            db, user_id=8, coin_id=launched["id"], side="sell", amount="40",
            limit_price_mora="3", time_in_force="gtc", action_id="order-halt-sell02",
        )
        await service.place_limit_order(
            db, user_id=9, coin_id=launched["id"], side="buy", amount="40",
            limit_price_mora="3", time_in_force="gtc", action_id="order-halt-buy002",
        )
        assert len(await service.match_market(db, coin_id=launched["id"])) == 1
        halt = await repo.market_halt(db, launched["id"])
        assert halt["active"] is True and halt["reason"] == "price_move_20pct_5m"
        market = await service.public_market(db, coin_id=launched["id"])
        assert "owner_id" not in market["coin"]
        assert all("user_id" not in row and "buyer_id" not in row for row in market["recent_trades"])
        stats = market["stats_24h"]
        assert stats["vwap_5m_price_micromora"] is not None
        assert stats["volume_5m_mora"] > 0
        assert stats["depth_5pct"]["total_mora"] >= 0
        assert stats["market_cap_mora"] > 0
        manual_halt = await service.manually_halt_market(
            db, actor_id=1, coin_id=launched["id"], minutes=60,
            public_reason="Техническая проверка расчётов рынка.", action_id="manual-halt-action-0001",
        )
        assert manual_halt["active"] is True and manual_halt["kind"] == "manual"
        assert manual_halt["public_reason"] == "Техническая проверка расчётов рынка."
        await repo.set_market_halt(
            db, coin_id=launched["id"], minutes=5, reason="price_move_20pct_5m",
            reference_price=2_000_000,
        )
        protected_manual_halt = await repo.market_halt(db, launched["id"])
        assert protected_manual_halt["kind"] == "manual"
        assert protected_manual_halt["public_reason"] == "Техническая проверка расчётов рынка."
        manual_replay = await service.manually_halt_market(
            db, actor_id=1, coin_id=launched["id"], minutes=60,
            public_reason="Техническая проверка расчётов рынка.", action_id="manual-halt-action-0001",
        )
        assert manual_replay["replayed"] is True
        try:
            await service.manually_halt_market(
                db, actor_id=1, coin_id=launched["id"], minutes=120,
                public_reason="Другая причина остановки рынка.", action_id="manual-halt-action-0001",
            )
            raise AssertionError("changed manual-halt replay was accepted")
        except IdempotencyConflict:
            pass
        public_halt = (await service.public_market(db, coin_id=launched["id"]))["stats_24h"]["halt"]
        assert public_halt["public_reason"] == "Техническая проверка расчётов рынка."
        assert set(public_halt) == {"active", "halted_until", "kind", "public_reason"}
        assert (await conn.fetchrow(
            "SELECT halt_reference_price_micromora FROM player_coin_market_state_v1 WHERE coin_id=$1",
            launched["id"],
        ))[0] is None
        assert await conn.fetchval(
            "SELECT COUNT(*) FROM player_coin_events_v1 WHERE coin_id=$1 AND event_type='market_halted_manual'",
            launched["id"],
        ) == 1

        failed = await service.create_coin(
            db, owner_id=10, name="Тихая монета", ticker="QUIET",
            initial_mora=10000, action_id="create-action-0010",
        )
        await db.execute(
            "UPDATE player_coins_v1 SET auction_starts_at=NOW()-INTERVAL '2 hours',"
            "auction_ends_at=NOW()-INTERVAL '1 second' WHERE id=?", (failed["id"],)
        )
        await db.commit()
        failed_result = await service.settle_auction(db, coin_id=failed["id"])
        assert failed_result["success"] is False
        owner = await conn.fetchrow("SELECT user_balance_mora,user_balance_zarniki FROM users WHERE user_tg_id=10")
        assert float(owner[0]) == 100000 and float(owner[1]) == 8000
    finally:
        await conn.close()

    conn, _ = await connect(dsn)
    try:
        row = await conn.fetchrow("SELECT user_balance_mora,user_balance_zarniki FROM users WHERE user_tg_id=2")
        assert float(row[0]) == 90000 and float(row[1]) == 8000
        assert await conn.fetchval("SELECT COUNT(*) FROM economic_operations WHERE user_id=2") == 1
        assert await conn.fetchval("SELECT COUNT(*) FROM player_coins_v1 WHERE owner_id=2") == 1
        assert await conn.fetchval("SELECT SUM(available_units) FROM player_coin_accounts_v1 WHERE coin_id=$1", first["id"]) == 1_000_000_000
        assert float(await conn.fetchval("SELECT treasury_mora FROM player_coin_mora_accounts_v1 WHERE coin_id=$1", first["id"])) == 10000
        assert float(await conn.fetchval("SELECT SUM(delta) FROM player_coin_mora_ledger_v1 WHERE coin_id=$1", first["id"])) == 10000
        assert await conn.fetchval("SELECT COUNT(*) FROM economic_operations WHERE user_id=3") == 0
        assert await conn.fetchval("SELECT COUNT(*) FROM economic_operations WHERE user_id=4") == 0
        assert await conn.fetchval("SELECT COUNT(*) FROM economic_operations WHERE user_id=6") == 0
        try:
            await conn.execute("UPDATE player_coin_events_v1 SET event_type='tampered' WHERE coin_id=$1", first["id"])
            raise AssertionError("append-only event was mutable")
        except asyncpg.RaiseError:
            pass
        try:
            await conn.execute("DELETE FROM player_coin_mora_ledger_v1 WHERE coin_id=$1", first["id"])
            raise AssertionError("append-only Mora custody ledger was mutable")
        except asyncpg.RaiseError:
            pass
    finally:
        await conn.close()
    original_due = repo.due_auction_ids
    original_settle = service.settle_auction
    async def fake_due(_db, limit=20):
        return ["poison", "healthy"]
    async def fake_settle(_db, *, coin_id):
        if coin_id == "poison":
            raise RuntimeError("broken row")
        return {"coin_id": coin_id, "success": True}
    repo.due_auction_ids = fake_due
    service.settle_auction = fake_settle
    try:
        isolated = await service.settle_due_auctions(None)
        assert isolated[0]["coin_id"] == "poison" and "error" in isolated[0]
        assert isolated[1] == {"coin_id": "healthy", "success": True}
    finally:
        repo.due_auction_ids = original_due
        service.settle_auction = original_settle
    print("PLAYER_EXCHANGE_V1_PG_OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, default="postgresql://postgres:postgres@127.0.0.1:5432/postgres")
    args = parser.parse_args()
    asyncio.run(main(args.dsn))
