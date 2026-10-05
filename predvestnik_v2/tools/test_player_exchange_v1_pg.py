#!/usr/bin/env python3
"""Loopback PostgreSQL proof for atomic player-coin creation."""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
from decimal import Decimal
from pathlib import Path
import sys
from urllib.parse import urlparse

import asyncpg
from fastapi.encoders import jsonable_encoder

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.economy_contract import IdempotencyConflict, InsufficientBalance
from core.player_exchange_shorts_v1 import SHORTS_FEATURE_FLAG_KEY
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
        assert await system_flags.is_enabled(db, SHORTS_FEATURE_FLAG_KEY) is False
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
        short_reserve = await conn.fetchrow(
            "SELECT available_mora,shorts_paused "
            "FROM player_coin_short_reserves_v1 WHERE coin_id=$1", launched["id"],
        )
        assert dict(short_reserve) == {
            "available_mora": Decimal("0"), "shorts_paused": False,
        }
        # Schema-only Shorts foundation: exact lender allocation cannot drift,
        # a frozen claim pauses new opens, and cross-lender claims are rejected.
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO player_coin_lending_positions_v1(coin_id,lender_id,loaned_units) VALUES($1,8,100)",
                launched["id"],
            )
            await conn.execute(
                "INSERT INTO player_coin_short_positions_v1"
                "(id,coin_id,borrower_id,action_id,status,initial_debt_units,outstanding_debt_units,"
                "posted_collateral_mora,locked_sale_proceeds_mora) "
                "VALUES('short-foundation-position',$1,9,'short-foundation-open','open',100,100,2,2)",
                launched["id"],
            )
            await conn.execute(
                "INSERT INTO player_coin_short_loans_v1"
                "(id,coin_id,position_id,lender_id,principal_units,outstanding_units) "
                "VALUES('short-foundation-loan',$1,'short-foundation-position',8,100,100)", launched["id"],
            )
        await conn.execute(
            "INSERT INTO player_coin_orders_v1"
            "(id,coin_id,user_id,actor_kind,short_position_id,action_id,side,time_in_force,"
            "limit_price_micromora,original_units,remaining_units,reserved_mora,status,closed_at) "
            "VALUES('short-foundation-sale',$1,9,'short','short-foundation-position',"
            "'short-foundation-sale','sell','ioc',100,100,0,0,'filled',NOW())",
            launched["id"],
        )
        try:
            await conn.execute(
                "INSERT INTO player_coin_orders_v1"
                "(id,coin_id,user_id,actor_kind,short_position_id,action_id,side,time_in_force,"
                "limit_price_micromora,original_units,remaining_units,reserved_mora) "
                "VALUES('short-foundation-invalid',$1,9,'player','short-foundation-position',"
                "'short-foundation-invalid','sell','ioc',100,100,100,0)",
                launched["id"],
            )
            raise AssertionError("player order was allowed to bind a Shorts position")
        except asyncpg.CheckViolationError:
            pass
        try:
            await conn.execute(
                "INSERT INTO player_coin_short_frozen_claims_v1"
                "(id,coin_id,position_id,loan_id,lender_id,principal_units,remaining_units) "
                "VALUES('short-foundation-cross',$1,'short-foundation-position','short-foundation-loan',9,100,100)",
                launched["id"],
            )
            raise AssertionError("cross-lender frozen claim was accepted")
        except asyncpg.ForeignKeyViolationError:
            pass
        async with conn.transaction():
            await conn.execute(
                "UPDATE player_coin_lending_positions_v1 SET loaned_units=0,frozen_units=100 "
                "WHERE coin_id=$1 AND lender_id=8", launched["id"],
            )
            await conn.execute(
                "UPDATE player_coin_short_positions_v1 SET status='frozen',outstanding_debt_units=0,closed_at=NOW() "
                "WHERE id='short-foundation-position'",
            )
            await conn.execute(
                "UPDATE player_coin_short_loans_v1 SET outstanding_units=0,frozen_units=100,closed_at=NOW() "
                "WHERE id='short-foundation-loan'",
            )
            await conn.execute(
                "INSERT INTO player_coin_short_frozen_claims_v1"
                "(id,coin_id,position_id,loan_id,lender_id,principal_units,remaining_units) "
                "VALUES('short-foundation-claim',$1,'short-foundation-position','short-foundation-loan',8,100,100)",
                launched["id"],
            )
        assert await conn.fetchval(
            "SELECT shorts_paused FROM player_coin_short_reserves_v1 WHERE coin_id=$1", launched["id"],
        ) is True
        for sql, args in (
            (
                "UPDATE player_coin_lending_positions_v1 SET frozen_units=0 WHERE coin_id=$1 AND lender_id=8",
                (launched["id"],),
            ),
            (
                "UPDATE player_coin_short_positions_v1 SET outstanding_debt_units=1 WHERE id='short-foundation-position'",
                (),
            ),
            (
                "UPDATE player_coin_short_reserves_v1 SET available_mora=-1 WHERE coin_id=$1",
                (launched["id"],),
            ),
        ):
            try:
                await conn.execute(sql, *args)
                raise AssertionError("inconsistent Shorts state was accepted")
            except (asyncpg.CheckViolationError, asyncpg.RaiseError):
                pass
        await conn.execute(
            "INSERT INTO player_coin_short_buyback_cycles_v1"
            "(coin_id,cycle_hour,reserve_snapshot_mora,budget_mora,action_id) "
            "VALUES($1,date_trunc('hour',NOW()),100,5,'short-foundation-cycle')", launched["id"],
        )
        try:
            await conn.execute(
                "UPDATE player_coin_short_buyback_cycles_v1 SET spent_mora=6 "
                "WHERE coin_id=$1 AND action_id='short-foundation-cycle'", launched["id"],
            )
            raise AssertionError("cycle spent beyond its fixed budget was accepted")
        except asyncpg.CheckViolationError:
            pass
        await conn.execute(
            "INSERT INTO player_coin_short_events_v1(id,coin_id,actor_id,event_type,action_id,payload_json) "
            "VALUES('short-foundation-event-1',$1,NULL,'foundation','short-foundation-event','{}'::jsonb)",
            launched["id"],
        )
        try:
            await conn.execute(
                "INSERT INTO player_coin_short_events_v1(id,coin_id,actor_id,event_type,action_id,payload_json) "
                "VALUES('short-foundation-event-2',$1,NULL,'foundation','short-foundation-event','{}'::jsonb)",
                launched["id"],
            )
            raise AssertionError("duplicate system Shorts receipt was accepted")
        except asyncpg.UniqueViolationError:
            pass
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
        await db.execute(
            "UPDATE player_coin_auction_settlements_v1 SET settled_at=NOW()-INTERVAL '10 days' WHERE coin_id=?",
            (launched["id"],),
        )
        await db.execute(
            "UPDATE player_coins_v1 SET launched_at=NULL,"
            "auction_starts_at=NOW()-INTERVAL '21 days',auction_ends_at=NOW()-INTERVAL '20 days' WHERE id=?",
            (launched["id"],),
        )
        await repo.ensure_tables(db)
        await db.commit()
        launch_times = await conn.fetchrow(
            "SELECT c.launched_at,s.settled_at,c.auction_ends_at FROM player_coins_v1 c "
            "JOIN player_coin_auction_settlements_v1 s ON s.coin_id=c.id WHERE c.id=$1",
            launched["id"],
        )
        assert launch_times["launched_at"] == launch_times["settled_at"]
        assert launch_times["launched_at"] != launch_times["auction_ends_at"]
        await db.execute(
            "UPDATE player_coins_v1 SET launched_at=NOW()-INTERVAL '6 days 23 hours' WHERE id=?",
            (launched["id"],),
        )
        await db.commit()
        assert (await repo.short_eligibility_metrics(db, coin_id=launched["id"]))["trading_days"] == 6
        short_gate = await service.short_eligibility(db, coin_id=launched["id"])
        assert short_gate["eligible"] is False and short_gate["shorts_enabled"] is False
        await db.execute(
            "UPDATE player_coins_v1 SET launched_at=(SELECT settled_at FROM player_coin_auction_settlements_v1 WHERE coin_id=?) "
            "WHERE id=?", (launched["id"], launched["id"]),
        )
        await db.commit()
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
        # Once the separate Shorts flag is deliberately enabled, new fee insurance
        # stays with this coin and cannot subsidise a different market.
        global_insurance_before = await conn.fetchval(
            "SELECT insurance_mora FROM player_exchange_fee_fund_v1 WHERE singleton=TRUE"
        )
        await db.execute("UPDATE system_flags SET enabled=1 WHERE key=?", (SHORTS_FEATURE_FLAG_KEY,))
        await db.commit()
        fee_short_sell = await service.place_limit_order(
            db, user_id=8, coin_id=launched["id"], side="sell", amount="10",
            limit_price_mora="2", time_in_force="gtc", action_id="shorts-fee-sell-0001",
        )
        fee_short_buy = await service.place_limit_order(
            db, user_id=9, coin_id=launched["id"], side="buy", amount="10",
            limit_price_mora="2", time_in_force="gtc", action_id="shorts-fee-buy-0001",
        )
        assert await service.match_market(db, coin_id=launched["id"])
        assert fee_short_sell["id"] != fee_short_buy["id"]
        assert await conn.fetchval(
            "SELECT insurance_mora FROM player_exchange_fee_fund_v1 WHERE singleton=TRUE"
        ) == global_insurance_before
        assert await conn.fetchval(
            "SELECT available_mora FROM player_coin_short_reserves_v1 WHERE coin_id=$1", launched["id"],
        ) > 0
        assert await conn.fetchval(
            "SELECT COUNT(*) FROM player_coin_short_reserve_ledger_v1 "
            "WHERE coin_id=$1 AND source_type='spot_fee'", launched["id"],
        ) == 1
        await db.execute("UPDATE system_flags SET enabled=0 WHERE key=?", (SHORTS_FEATURE_FLAG_KEY,))
        await db.commit()
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
        assert int(token8_after["available_units"]) == 19_960_000
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
        recovery8 = await service.player_recovery_state(db, user_id=8)
        assert recovery8["trading_enabled"] is False and recovery8["can_cancel_open_orders"] is True
        recovery8_orders = recovery8["orders"]["items"]
        assert any(row["id"] == disabled_sell["id"] for row in recovery8_orders)
        assert all(row["id"] != disabled_buy["id"] for row in recovery8_orders)
        assert all("user_id" not in row and "action_id" not in row for row in recovery8_orders)
        assert recovery8["holdings"]["items"] and recovery8["auction_bids"]["items"]
        assert all("id" not in row for row in recovery8["auction_bids"]["items"])
        json.dumps(jsonable_encoder(recovery8))
        try:
            await service.player_recovery_state(db, user_id=8, orders_cursor="not-a-cursor")
            raise AssertionError("invalid recovery cursor accepted")
        except PlayerExchangePolicyError:
            pass
        wrong_kind_cursor = base64.urlsafe_b64encode(json.dumps({
            "k": "bids", "r": 1, "t": "2026-01-01T00:00:00+00:00", "i": "bid",
        }).encode()).decode().rstrip("=")
        try:
            await service.player_recovery_state(db, user_id=8, orders_cursor=wrong_kind_cursor)
            raise AssertionError("cross-list recovery cursor accepted")
        except PlayerExchangePolicyError:
            pass
        malformed_cursors = [
            {"k": "orders", "r": 1, "t": "not-a-time", "i": "order"},
            {"k": "orders", "r": True, "t": "2026-01-01T00:00:00+00:00", "i": "order"},
            {"k": "orders", "r": 2, "t": "2026-01-01T00:00:00+00:00", "i": "order"},
            {"k": "orders", "r": 1, "t": "2026-01-01T00:00:00", "i": "order"},
            {"k": "orders", "r": 1, "t": "2026-01-01T00:00:00+00:00", "i": ""},
            {"k": "orders", "r": 1, "t": "2026-01-01T00:00:00+00:00", "i": "order", "x": 1},
        ]
        for malformed in malformed_cursors:
            encoded = base64.urlsafe_b64encode(json.dumps(malformed).encode()).decode().rstrip("=")
            try:
                await service.player_recovery_state(db, user_id=8, orders_cursor=encoded)
                raise AssertionError(f"structured malformed cursor accepted: {malformed}")
            except PlayerExchangePolicyError:
                pass
        try:
            await service.player_recovery_state(db, user_id=3)
            raise AssertionError("empty disabled recovery disclosed hidden exchange")
        except service.PlayerExchangeUnavailable:
            pass

        recovery_order_ids = {f"recovery-page-{index:03d}" for index in range(101)}
        await conn.executemany(
            "INSERT INTO player_coin_orders_v1"
            "(id,coin_id,user_id,actor_kind,action_id,side,time_in_force,limit_price_micromora,"
            "original_units,remaining_units,status,created_at) "
            "VALUES($1,$2,11,'player',$3,'sell','gtc',2000000,10000,10000,'open',"
            "NOW()-($4::integer*INTERVAL '1 millisecond'))",
            [(order_id, launched["id"], f"recovery-action-{index:03d}", index)
             for index, order_id in enumerate(sorted(recovery_order_ids))],
        )
        seen_recovery_ids = []
        cursor = None
        for _ in range(3):
            page = await service.player_recovery_state(
                db, user_id=11, limit=100, orders_cursor=cursor,
            )
            seen_recovery_ids.extend(
                row["id"] for row in page["orders"]["items"] if row["id"] in recovery_order_ids
            )
            cursor = page["orders"]["next_cursor"]
            if not cursor:
                break
        assert set(seen_recovery_ids) == recovery_order_ids
        assert len(seen_recovery_ids) == len(set(seen_recovery_ids)) == 101
        recovery9 = await service.player_recovery_state(db, user_id=9)
        assert all(row["id"] != disabled_sell["id"] for row in recovery9["orders"]["items"])
        await conn.execute("DELETE FROM player_coin_orders_v1 WHERE id LIKE 'recovery-page-%'")
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

        # Full kill-switch exercise: crossed orders stay untouched during a
        # manual halt, cancellation stays available, and matching resumes only
        # after the server-owned deadline has elapsed.
        halt_sell = await service.place_limit_order(
            db, user_id=8, coin_id=launched["id"], side="sell", amount="100",
            limit_price_mora="0.1", time_in_force="gtc", action_id="halt-e2e-sell-0001",
        )
        halt_buy = await service.place_limit_order(
            db, user_id=9, coin_id=launched["id"], side="buy", amount="100",
            limit_price_mora="10", time_in_force="gtc", action_id="halt-e2e-buy-0001",
        )
        assert await service.match_market(db, coin_id=launched["id"]) == []
        assert (await repo.get_order(db, halt_sell["id"]))["status"] == "open"
        assert (await repo.get_order(db, halt_buy["id"]))["status"] == "open"
        assert (await service.cancel_order(db, user_id=9, order_id=halt_buy["id"]))["status"] == "cancelled"
        await db.execute(
            "UPDATE player_coin_market_state_v1 SET halted_until=NOW()-INTERVAL '1 second' WHERE coin_id=?",
            (launched["id"],),
        )
        await db.commit()
        resume_buy = await service.place_limit_order(
            db, user_id=9, coin_id=launched["id"], side="buy", amount="100",
            limit_price_mora="10", time_in_force="gtc", action_id="halt-e2e-resume-buy",
        )
        resumed_trades = await service.match_market(db, coin_id=launched["id"])
        assert resumed_trades
        assert (await repo.get_order(db, halt_sell["id"]))["status"] == "filled"
        assert (await repo.get_order(db, resume_buy["id"]))["status"] in {"filled", "open"}

        # The owner's 20% allocation has a 30-day cliff, then vests linearly for 180 days.
        await db.execute(
            "UPDATE player_coins_v1 SET launched_at=NOW()-INTERVAL '120 days' WHERE id=?",
            (launched["id"],),
        )
        await db.commit()
        circulation_before_vesting = int(await conn.fetchval(
            "SELECT circulating_units FROM player_coins_v1 WHERE id=$1", launched["id"],
        ))
        vesting_quote = service._project_owner_vesting(
            await repo.owner_vesting_state(db, launched["id"])
        )
        confirmed_vesting_units = int(vesting_quote["claimable_units"])
        await db.execute(
            "UPDATE player_coins_v1 SET launched_at=launched_at-INTERVAL '1 day' WHERE id=?",
            (launched["id"],),
        )
        await db.commit()
        vesting_claim = await service.claim_owner_vesting(
            db, owner_id=7, coin_id=launched["id"], units=confirmed_vesting_units,
            action_id="owner-vesting-claim-0001",
        )
        assert vesting_claim["units"] == confirmed_vesting_units
        assert 99_000_000 <= vesting_claim["units"] <= 101_000_000
        assert vesting_claim["replayed"] is False
        vesting_replay = await service.claim_owner_vesting(
            db, owner_id=7, coin_id=launched["id"], units=confirmed_vesting_units,
            action_id="owner-vesting-claim-0001",
        )
        assert vesting_replay["units"] == vesting_claim["units"] and vesting_replay["replayed"] is True
        try:
            await service.claim_owner_vesting(
                db, owner_id=7, coin_id=launched["id"], units=confirmed_vesting_units + 1,
                action_id="owner-vesting-claim-0001",
            )
            raise AssertionError("vesting replay accepted another confirmed amount")
        except IdempotencyConflict:
            pass
        assert int(await conn.fetchval(
            "SELECT circulating_units FROM player_coins_v1 WHERE id=$1", launched["id"],
        )) == circulation_before_vesting + vesting_claim["units"]
        try:
            await service.claim_owner_vesting(
                db, owner_id=8, coin_id=launched["id"], units=1,
                action_id="owner-vesting-foreign",
            )
            raise AssertionError("foreign owner claimed vesting")
        except PlayerExchangePolicyError:
            pass
        for index in range(60):
            await repo.append_event(
                db, coin_id=launched["id"], actor_id=None, event_type="spot_trade",
                action_id=f"journal-noise-trade-{index}",
                payload={"units": 1000, "price_micromora": 1_000_000, "gross_mora": "1"},
            )
        await db.commit()
        vesting_market = await service.public_market(db, coin_id=launched["id"])
        assert vesting_market["owner_vesting"]["claimed_units"] == vesting_claim["units"]
        vesting_events = [
            row for row in vesting_market["journal"] if row["event_type"] == "owner_vesting_claimed"
        ]
        assert vesting_events and vesting_events[0]["details"]["units"] == vesting_claim["units"]
        created_events = [row for row in vesting_market["journal"] if row["event_type"] == "coin_created"]
        assert created_events and "economy_operation_id" not in created_events[0]["details"]

        # Owner treasury actions reserve only public treasury balances and have public receipts.
        treasury_token_before = int(await conn.fetchval(
            "SELECT available_units FROM player_coin_accounts_v1 "
            "WHERE coin_id=$1 AND account_kind='treasury'", launched["id"],
        ))
        supply_before_burn = int(await conn.fetchval(
            "SELECT total_supply_units FROM player_coins_v1 WHERE id=$1", launched["id"],
        ))
        burned = await service.burn_treasury(
            db, owner_id=7, coin_id=launched["id"], amount="1000",
            action_id="treasury-burn-0001",
        )
        assert burned["units"] == 1_000_000 and burned["replayed"] is False
        burned_replay = await service.burn_treasury(
            db, owner_id=7, coin_id=launched["id"], amount="1000",
            action_id="treasury-burn-0001",
        )
        assert burned_replay["replayed"] is True
        assert int(await conn.fetchval(
            "SELECT total_supply_units FROM player_coins_v1 WHERE id=$1", launched["id"],
        )) == supply_before_burn - 1_000_000
        assert int(await conn.fetchval(
            "SELECT available_units FROM player_coin_accounts_v1 "
            "WHERE coin_id=$1 AND account_kind='treasury'", launched["id"],
        )) == treasury_token_before - 1_000_000
        treasury_sell = await service.place_treasury_order(
            db, owner_id=7, coin_id=launched["id"], side="sell", amount="100",
            limit_price_mora="999", action_id="treasury-sell-0001",
        )
        assert treasury_sell["actor_kind"] == "treasury"
        assert treasury_sell["treasury_token_bucket"] == "treasury"
        treasury_sell_cancelled = await service.cancel_treasury_order(
            db, owner_id=7, order_id=treasury_sell["id"], action_id="treasury-sell-cancel-0001",
        )
        assert treasury_sell_cancelled["status"] == "cancelled"
        try:
            await service.place_treasury_order(
                db, owner_id=7, coin_id=launched["id"], side="buy", amount="10",
                limit_price_mora="0.000001", action_id="treasury-dust-buy",
            )
            raise AssertionError("dust treasury order accepted")
        except PlayerExchangePolicyError:
            pass
        treasury_buy = await service.place_treasury_order(
            db, owner_id=7, coin_id=launched["id"], side="buy", amount="10",
            limit_price_mora="1", action_id="treasury-buy-0001",
        )
        assert treasury_buy["actor_kind"] == "treasury" and treasury_buy["status"] == "open"
        try:
            await service.place_treasury_order(
                db, owner_id=7, coin_id=launched["id"], side="sell", amount="10",
                limit_price_mora="1", action_id="treasury-self-cross-rejected",
            )
            raise AssertionError("crossing treasury sell was accepted")
        except PlayerExchangePolicyError:
            pass
        # A crossed treasury pair from an older deployment is released instead
        # of repeatedly rolling back against the immutable no-self-trade check.
        await repo.reserve_treasury_tokens(
            db, coin_id=launched["id"], units=10_000, bucket="treasury",
        )
        legacy_treasury_sell = await repo.insert_order(
            db, coin_id=launched["id"], user_id=7, action_id="legacy-treasury-self-cross",
            side="sell", time_in_force="gtc", price=1_000_000, units=10_000,
            reserved_mora=Decimal("0"), reserve_operation_id=None, actor_kind="treasury",
            treasury_token_bucket="treasury",
        )
        await db.execute(
            "UPDATE player_coin_market_state_v1 SET halted_until=NOW()-INTERVAL '1 second' WHERE coin_id=?",
            (launched["id"],),
        )
        await db.commit()
        await service.match_market(db, coin_id=launched["id"], max_trades=500)
        assert (await repo.get_order(db, legacy_treasury_sell["id"]))["status"] == "cancelled"
        assert (await repo.get_order(db, treasury_buy["id"]))["status"] == "open"
        try:
            await service.place_treasury_order(
                db, owner_id=8, coin_id=launched["id"], side="buy", amount="1",
                limit_price_mora="10", action_id="treasury-foreign-buy",
            )
            raise AssertionError("foreign owner managed treasury")
        except PlayerExchangePolicyError:
            pass
        treasury_market = await service.public_market(db, coin_id=launched["id"])
        assert any(row["event_type"] == "treasury_burned" for row in treasury_market["journal"])
        assert any(row["event_type"] == "treasury_order_placed" for row in treasury_market["journal"])

        # An owner may add Mora, while withdrawal is delayed, capped, cancellable and replay-safe.
        owner_mora_before_add = Decimal(str(await conn.fetchval(
            "SELECT user_balance_mora FROM users WHERE user_tg_id=7",
        )))
        treasury_before_add = Decimal(str((await repo.public_treasury_state(db, launched["id"]))["treasury_mora"]))
        liquidity_add = await service.add_treasury_liquidity(
            db, owner_id=7, coin_id=launched["id"], amount_mora="1000",
            action_id="liquidity-add-0001",
        )
        assert Decimal(liquidity_add["amount_mora"]) == Decimal("1000") and not liquidity_add["replayed"]
        liquidity_add_replay = await service.add_treasury_liquidity(
            db, owner_id=7, coin_id=launched["id"], amount_mora="1000",
            action_id="liquidity-add-0001",
        )
        assert liquidity_add_replay["replayed"] is True
        assert Decimal(str((await repo.public_treasury_state(db, launched["id"]))["treasury_mora"])) == treasury_before_add + Decimal("1000")
        assert Decimal(str(await conn.fetchval(
            "SELECT user_balance_mora FROM users WHERE user_tg_id=7",
        ))) == owner_mora_before_add - Decimal("1000")
        await db.execute(
            "UPDATE player_coins_v1 SET launched_at=NOW()-INTERVAL '29 days' WHERE id=?", (launched["id"],),
        )
        await db.commit()
        try:
            await service.request_liquidity_withdrawal(
                db, owner_id=7, coin_id=launched["id"], amount_mora="1", action_id="liquidity-lock-reject",
            )
            raise AssertionError("liquidity withdrew before 30-day lock")
        except PlayerExchangePolicyError:
            pass
        await db.execute(
            "UPDATE player_coins_v1 SET launched_at=NOW()-INTERVAL '31 days' WHERE id=?", (launched["id"],),
        )
        await db.commit()
        treasury_for_withdrawal = Decimal(str((await repo.public_treasury_state(db, launched["id"]))["treasury_mora"]))
        withdrawal_amount = (treasury_for_withdrawal * Decimal("0.1")).quantize(Decimal("0.000001"))
        try:
            await service.request_liquidity_withdrawal(
                db, owner_id=7, coin_id=launched["id"], amount_mora=str(withdrawal_amount + 1),
                action_id="liquidity-cap-reject",
            )
            raise AssertionError("liquidity withdrawal exceeded 10% cap")
        except PlayerExchangePolicyError:
            pass
        withdrawal = await service.request_liquidity_withdrawal(
            db, owner_id=7, coin_id=launched["id"], amount_mora=str(withdrawal_amount),
            action_id="liquidity-withdraw-0001",
        )
        assert withdrawal["status"] == "pending" and not withdrawal["replayed"]
        withdrawal_replay = await service.request_liquidity_withdrawal(
            db, owner_id=7, coin_id=launched["id"], amount_mora=str(withdrawal_amount),
            action_id="liquidity-withdraw-0001",
        )
        assert withdrawal_replay["id"] == withdrawal["id"] and withdrawal_replay["replayed"] is True
        try:
            await service.cancel_liquidity_withdrawal(
                db, owner_id=8, withdrawal_id=withdrawal["id"], action_id="liquidity-cancel-foreign",
            )
            raise AssertionError("foreign owner cancelled liquidity withdrawal")
        except PlayerExchangePolicyError:
            pass
        await db.execute("UPDATE system_flags SET enabled=0 WHERE key=?", (service.FEATURE_FLAG_KEY,))
        await db.commit()
        cancelled_withdrawal = await service.cancel_liquidity_withdrawal(
            db, owner_id=7, withdrawal_id=withdrawal["id"], action_id="liquidity-cancel-0001",
        )
        assert cancelled_withdrawal["status"] == "cancelled"
        await db.execute("UPDATE system_flags SET enabled=1 WHERE key=?", (service.FEATURE_FLAG_KEY,))
        await db.commit()
        due_withdrawal = await service.request_liquidity_withdrawal(
            db, owner_id=7, coin_id=launched["id"], amount_mora=str(withdrawal_amount),
            action_id="liquidity-withdraw-0002",
        )
        owner_mora_before_withdrawal = Decimal(str(await conn.fetchval(
            "SELECT user_balance_mora FROM users WHERE user_tg_id=7",
        )))
        await db.execute(
            "UPDATE player_coin_liquidity_withdrawals_v1 SET executes_at=NOW()-INTERVAL '1 second' WHERE id=?",
            (due_withdrawal["id"],),
        )
        await db.commit()
        executed_withdrawals = await service.execute_due_liquidity_withdrawals(db)
        assert any(row.get("id") == due_withdrawal["id"] and row["status"] == "executed" for row in executed_withdrawals)
        assert Decimal(str(await conn.fetchval(
            "SELECT user_balance_mora FROM users WHERE user_tg_id=7",
        ))) == owner_mora_before_withdrawal + withdrawal_amount
        try:
            await service.request_liquidity_withdrawal(
                db, owner_id=7, coin_id=launched["id"], amount_mora="1", action_id="liquidity-cooldown-reject",
            )
            raise AssertionError("liquidity withdrawal ignored 7-day cooldown")
        except PlayerExchangePolicyError:
            pass
        liquidity_market = await service.public_market(db, coin_id=launched["id"])
        assert any(row["status"] == "executed" for row in liquidity_market["liquidity_withdrawals"])
        assert any(row["event_type"] == "liquidity_withdrawal_executed" for row in liquidity_market["journal"])

        # Owner emissions are public, delayed, capped and treasury-only.
        circulation = int(await conn.fetchval(
            "SELECT circulating_units FROM player_coins_v1 WHERE id=$1", launched["id"],
        ))
        treasury_sell_before_emission = await service.place_treasury_order(
            db, owner_id=7, coin_id=launched["id"], side="sell", amount="20",
            limit_price_mora="999", action_id="emission-treasury-sell-before",
        )
        try:
            await service.request_emission(
                db, owner_id=7, coin_id=launched["id"], amount="1000",
                reason="Плановое расширение публичной казны.", action_id="emission-request-with-treasury-sell",
            )
            raise AssertionError("emission with an existing treasury sell was accepted")
        except PlayerExchangePolicyError:
            pass
        await service.cancel_treasury_order(
            db, owner_id=7, order_id=treasury_sell_before_emission["id"],
            action_id="emission-treasury-sell-before-cancel",
        )
        await repo.credit_bid_tokens(db, coin_id=launched["id"], bidder_id=7, units=20_000)
        owner_sell = await service.place_limit_order(
            db, user_id=7, coin_id=launched["id"], side="sell", amount="20",
            limit_price_mora="1", time_in_force="gtc", action_id="emission-owner-sell-before",
        )
        try:
            await service.request_emission(
                db, owner_id=7, coin_id=launched["id"], amount="1000",
                reason="Плановое расширение публичной казны.", action_id="emission-request-with-sell",
            )
            raise AssertionError("emission with an existing owner sell was accepted")
        except PlayerExchangePolicyError:
            pass
        await service.cancel_order(db, user_id=7, order_id=owner_sell["id"])
        emission = await service.request_emission(
            db, owner_id=7, coin_id=launched["id"], amount="1000",
            reason="Плановое расширение публичной казны.", action_id="emission-request-0001",
        )
        replayed_emission = await service.request_emission(
            db, owner_id=7, coin_id=launched["id"], amount="1000",
            reason="Плановое расширение публичной казны.", action_id="emission-request-0001",
        )
        assert replayed_emission["id"] == emission["id"] and replayed_emission["replayed"] is True
        assert emission["circulation_snapshot_units"] == circulation
        assert emission["projected_total_supply_units"] == int(await conn.fetchval(
            "SELECT total_supply_units FROM player_coins_v1 WHERE id=$1", launched["id"],
        )) + 1_000_000
        try:
            await service.cancel_treasury_order(
                db, owner_id=7, order_id=treasury_buy["id"], action_id="treasury-buy-cancel-blocked",
            )
            raise AssertionError("supporting treasury buy cancelled during pending emission")
        except PlayerExchangePolicyError:
            pass
        owner_buy = await service.place_limit_order(
            db, user_id=7, coin_id=launched["id"], side="buy", amount="20",
            limit_price_mora="0.5", time_in_force="gtc", action_id="emission-owner-buy-ok",
        )
        assert owner_buy["status"] == "open"
        await service.cancel_order(db, user_id=7, order_id=owner_buy["id"])
        try:
            await service.place_limit_order(
                db, user_id=7, coin_id=launched["id"], side="sell", amount="20",
                limit_price_mora="1", time_in_force="gtc", action_id="emission-owner-sell-blocked",
            )
            raise AssertionError("owner sold while emission was pending")
        except PlayerExchangePolicyError:
            pass
        try:
            await service.place_protected_market_order(
                db, user_id=7, coin_id=launched["id"], side="sell", amount="20",
                slippage_percent=3, action_id="emission-owner-ioc-sell-blocked",
            )
            raise AssertionError("owner protected-sold while emission was pending")
        except PlayerExchangePolicyError:
            pass
        try:
            await service.request_emission(
                db, owner_id=7, coin_id=launched["id"], amount=str(circulation // 1000),
                reason="Слишком большая попытка эмиссии монеты.", action_id="emission-request-too-large",
            )
            raise AssertionError("oversized emission was accepted")
        except PlayerExchangePolicyError:
            pass
        try:
            await service.cancel_emission(
                db, owner_id=8, emission_id=emission["id"], action_id="emission-cancel-foreign",
            )
            raise AssertionError("foreign owner cancelled emission")
        except PlayerExchangePolicyError:
            pass
        await db.execute("UPDATE system_flags SET enabled=0 WHERE key=?", (service.FEATURE_FLAG_KEY,))
        await db.commit()
        disabled_owner_recovery = await service.player_recovery_state(db, user_id=7)
        recovered_owned_coin = next(
            row for row in disabled_owner_recovery["owned_coins"]["items"]
            if row["coin_id"] == launched["id"]
        )
        assert disabled_owner_recovery["trading_enabled"] is False
        assert recovered_owned_coin["pending_emission_id"] == emission["id"]
        assert recovered_owned_coin["pending_emission_units"] == 1_000_000
        assert recovered_owned_coin["emission_requested_at"] is not None
        assert recovered_owned_coin["emission_executes_at"] is not None
        assert recovered_owned_coin["emission_can_cancel"] is True
        recovered_treasury_buy = next(
            row for row in disabled_owner_recovery["orders"]["items"]
            if row["id"] == treasury_buy["id"]
        )
        assert recovered_treasury_buy["actor_kind"] == "treasury"
        cancelled = await service.cancel_emission(
            db, owner_id=7, emission_id=emission["id"], action_id="emission-cancel-0001",
        )
        assert cancelled["status"] == "cancelled"
        treasury_buy_cancelled = await service.cancel_treasury_order(
            db, owner_id=7, order_id=treasury_buy["id"], action_id="treasury-buy-cancel-0001",
        )
        assert treasury_buy_cancelled["status"] == "cancelled"
        await db.execute("UPDATE system_flags SET enabled=1 WHERE key=?", (service.FEATURE_FLAG_KEY,))
        await db.execute(
            "UPDATE player_coin_emissions_v1 SET requested_at=NOW()-INTERVAL '8 days' WHERE id=?",
            (emission["id"],),
        )
        await db.commit()
        due = await service.request_emission(
            db, owner_id=7, coin_id=launched["id"], amount="2000",
            reason="Вторая публичная эмиссия после периода ожидания.", action_id="emission-request-0002",
        )
        supply_before = int(await conn.fetchval(
            "SELECT total_supply_units FROM player_coins_v1 WHERE id=$1", launched["id"],
        ))
        treasury_before = int(await conn.fetchval(
            "SELECT available_units FROM player_coin_accounts_v1 WHERE coin_id=$1 AND account_kind='treasury'",
            launched["id"],
        ))
        await db.execute("UPDATE player_coin_emissions_v1 SET executes_at=NOW()-INTERVAL '1 second' WHERE id=?", (due["id"],))
        await db.commit()
        executed = await service.execute_due_emissions(db)
        assert any(row.get("id") == due["id"] and row["status"] == "executed" for row in executed)
        assert int(await conn.fetchval(
            "SELECT total_supply_units FROM player_coins_v1 WHERE id=$1", launched["id"],
        )) == supply_before + 2_000_000
        assert int(await conn.fetchval(
            "SELECT available_units FROM player_coin_accounts_v1 WHERE coin_id=$1 AND account_kind='treasury'",
            launched["id"],
        )) == treasury_before + 2_000_000
        public_emissions = (await service.public_market(db, coin_id=launched["id"]))["emissions"]
        assert public_emissions[0]["status"] == "executed" and "owner_id" not in public_emissions[0]
        assert public_emissions[0]["can_cancel"] is False
        assert public_emissions[0]["executed_at"] is not None
        assert public_emissions[0]["circulation_snapshot_units"] == circulation
        assert public_emissions[0]["projected_total_supply_units"] == supply_before + 2_000_000

        # The first live Shorts writer is the voluntary pool only: it must be
        # explicitly enabled, replay-safe and unable to return unavailable units.
        lender_tokens_before = int((await repo.get_player_coin_account(
            db, coin_id=launched["id"], user_id=8,
        ))["available_units"])
        await db.execute("UPDATE system_flags SET enabled=1 WHERE key=?", (SHORTS_FEATURE_FLAG_KEY,))
        await db.commit()
        deposited = await service.deposit_lending_units(
            db, user_id=8, coin_id=launched["id"], amount="10", action_id="lending-deposit-0001",
        )
        assert deposited["replayed"] is False and int(deposited["position"]["available_units"]) == 10_000
        deposit_replay = await service.deposit_lending_units(
            db, user_id=8, coin_id=launched["id"], amount="10", action_id="lending-deposit-0001",
        )
        assert deposit_replay["replayed"] is True
        withdrawn = await service.withdraw_lending_units(
            db, user_id=8, coin_id=launched["id"], amount="4", action_id="lending-withdraw-0001",
        )
        assert withdrawn["replayed"] is False and int(withdrawn["position"]["available_units"]) == 6_000
        try:
            await service.withdraw_lending_units(
                db, user_id=8, coin_id=launched["id"], amount="7", action_id="lending-withdraw-excess",
            )
            raise AssertionError("withdrawal above free lender balance was accepted")
        except PlayerExchangePolicyError:
            pass
        assert int((await repo.get_player_coin_account(
            db, coin_id=launched["id"], user_id=8,
        ))["available_units"]) == lender_tokens_before - 6_000
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO player_coin_short_positions_v1"
                "(id,coin_id,borrower_id,action_id,status,initial_debt_units,outstanding_debt_units,"
                "posted_collateral_mora,locked_sale_proceeds_mora) "
                "VALUES('short-allocation-position',$1,9,'short-allocation-open','open',4000,4000,8,4)",
                launched["id"],
            )
            allocation = await repo.allocate_lending_units(
                db, coin_id=launched["id"], position_id="short-allocation-position", units=4_000,
            )
        assert [(row["lender_id"], row["principal_units"]) for row in allocation] == [(8, 4_000)]
        allocated_lender = await repo.get_lending_position(db, coin_id=launched["id"], lender_id=8)
        assert int(allocated_lender["available_units"]) == 2_000 and int(allocated_lender["loaned_units"]) == 4_000
        await db.execute("UPDATE system_flags SET enabled=0 WHERE key=?", (SHORTS_FEATURE_FLAG_KEY,))
        await db.commit()
        try:
            await service.deposit_lending_units(
                db, user_id=8, coin_id=launched["id"], amount="1", action_id="lending-disabled-0001",
            )
            raise AssertionError("disabled Shorts pool accepted a deposit")
        except service.PlayerExchangeUnavailable:
            pass

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
