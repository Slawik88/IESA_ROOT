"""PostgreSQL persistence for player-created coins; no legacy crypto coupling."""
from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

from core.player_exchange_v1 import PRICE_SCALE, TOKEN_SCALE

SCHEMA_VERSION = "player-exchange-schema-v4-market-safety-2026-09-27"


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coins_v1 (
            id TEXT PRIMARY KEY,
            owner_id BIGINT NOT NULL REFERENCES users(user_tg_id) ON DELETE RESTRICT,
            name TEXT NOT NULL,
            name_key TEXT NOT NULL UNIQUE,
            ticker TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK (status IN ('auction','active','failed','archived','halted')),
            rules_version TEXT NOT NULL,
            genesis_units BIGINT NOT NULL CHECK (genesis_units > 0),
            circulating_units BIGINT NOT NULL DEFAULT 0 CHECK (circulating_units >= 0),
            initial_mora BIGINT NOT NULL CHECK (initial_mora > 0),
            creation_operation_id TEXT NOT NULL UNIQUE REFERENCES economic_operations(id) ON DELETE RESTRICT,
            auction_starts_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            auction_ends_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (auction_ends_at > auction_starts_at)
        )
    """)
    await db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_player_coin_owner_live_v1 "
        "ON player_coins_v1(owner_id) WHERE status IN ('auction','active','halted')"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_accounts_v1 (
            coin_id TEXT NOT NULL REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            account_key TEXT NOT NULL,
            account_kind TEXT NOT NULL CHECK (account_kind IN
                ('player','auction','owner_locked','treasury','market_reserve')),
            user_id BIGINT NULL REFERENCES users(user_tg_id) ON DELETE RESTRICT,
            available_units BIGINT NOT NULL DEFAULT 0 CHECK (available_units >= 0),
            reserved_units BIGINT NOT NULL DEFAULT 0 CHECK (reserved_units >= 0),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (coin_id, account_key),
            CHECK ((account_kind='player' AND user_id IS NOT NULL) OR
                   (account_kind<>'player' AND user_id IS NULL))
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_events_v1 (
            id TEXT PRIMARY KEY,
            coin_id TEXT NOT NULL REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            actor_id BIGINT NULL,
            event_type TEXT NOT NULL,
            action_id TEXT NOT NULL,
            payload_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (actor_id, action_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_mora_accounts_v1 (
            coin_id TEXT PRIMARY KEY REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            treasury_mora NUMERIC(24,6) NOT NULL DEFAULT 0 CHECK (treasury_mora >= 0),
            insurance_mora NUMERIC(24,6) NOT NULL DEFAULT 0 CHECK (insurance_mora >= 0),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_auction_bids_v1 (
            id TEXT PRIMARY KEY,
            coin_id TEXT NOT NULL REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            bidder_id BIGINT NOT NULL REFERENCES users(user_tg_id) ON DELETE RESTRICT,
            action_id TEXT NOT NULL,
            max_price_micromora BIGINT NOT NULL CHECK (max_price_micromora > 0),
            escrow_mora BIGINT NOT NULL CHECK (escrow_mora > 0),
            economy_operation_id TEXT NOT NULL UNIQUE REFERENCES economic_operations(id) ON DELETE RESTRICT,
            status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','won','refunded')),
            allocated_units BIGINT NOT NULL DEFAULT 0 CHECK (allocated_units >= 0),
            cost_mora NUMERIC(24,6) NOT NULL DEFAULT 0 CHECK (cost_mora >= 0),
            refund_operation_id TEXT NULL UNIQUE REFERENCES economic_operations(id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (bidder_id, action_id),
            UNIQUE (coin_id, bidder_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_auction_settlements_v1 (
            coin_id TEXT PRIMARY KEY REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            success BOOLEAN NOT NULL,
            clearing_price_micromora BIGINT NOT NULL,
            sold_units BIGINT NOT NULL,
            raised_mora NUMERIC(24,6) NOT NULL,
            settled_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_orders_v1 (
            id TEXT PRIMARY KEY,
            coin_id TEXT NOT NULL REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            user_id BIGINT NOT NULL REFERENCES users(user_tg_id) ON DELETE RESTRICT,
            action_id TEXT NOT NULL,
            side TEXT NOT NULL CHECK (side IN ('buy','sell')),
            time_in_force TEXT NOT NULL CHECK (time_in_force IN ('gtc','ioc')),
            limit_price_micromora BIGINT NOT NULL CHECK (limit_price_micromora > 0),
            original_units BIGINT NOT NULL CHECK (original_units > 0),
            remaining_units BIGINT NOT NULL CHECK (remaining_units >= 0),
            reserved_mora NUMERIC(24,6) NOT NULL DEFAULT 0 CHECK (reserved_mora >= 0),
            spent_mora NUMERIC(24,6) NOT NULL DEFAULT 0 CHECK (spent_mora >= 0),
            status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','filled','cancelled')),
            reserve_operation_id TEXT NULL UNIQUE REFERENCES economic_operations(id) ON DELETE RESTRICT,
            release_operation_id TEXT NULL UNIQUE REFERENCES economic_operations(id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            closed_at TIMESTAMPTZ NULL,
            UNIQUE (user_id,action_id)
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_player_coin_order_book_v1 ON player_coin_orders_v1"
        "(coin_id,status,side,limit_price_micromora,created_at,id)"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_trades_v1 (
            id TEXT PRIMARY KEY,
            coin_id TEXT NOT NULL REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            buy_order_id TEXT NOT NULL REFERENCES player_coin_orders_v1(id) ON DELETE RESTRICT,
            sell_order_id TEXT NOT NULL REFERENCES player_coin_orders_v1(id) ON DELETE RESTRICT,
            buyer_id BIGINT NOT NULL,
            seller_id BIGINT NOT NULL,
            units BIGINT NOT NULL CHECK (units > 0),
            price_micromora BIGINT NOT NULL CHECK (price_micromora > 0),
            gross_mora NUMERIC(24,6) NOT NULL CHECK (gross_mora > 0),
            buyer_fee_mora NUMERIC(24,6) NOT NULL CHECK (buyer_fee_mora >= 0),
            seller_fee_mora NUMERIC(24,6) NOT NULL CHECK (seller_fee_mora >= 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (buyer_id <> seller_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_exchange_fee_fund_v1 (
            singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK(singleton),
            insurance_mora NUMERIC(24,6) NOT NULL DEFAULT 0 CHECK(insurance_mora >= 0),
            burned_mora NUMERIC(24,6) NOT NULL DEFAULT 0 CHECK(burned_mora >= 0)
        )
    """)
    await db.execute(
        "INSERT INTO player_exchange_fee_fund_v1(singleton) VALUES(TRUE) ON CONFLICT DO NOTHING"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_market_state_v1 (
            coin_id TEXT PRIMARY KEY REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            halted_until TIMESTAMPTZ NULL,
            halt_reason TEXT NULL,
            halt_reference_price_micromora BIGINT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE OR REPLACE FUNCTION prevent_player_coin_trade_mutation_v1()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'player_coin_trades_v1 is append-only'; END; $$
    """)
    await db.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger
                WHERE tgname='trg_player_coin_trades_immutable_v1'
                AND tgrelid='player_coin_trades_v1'::regclass AND NOT tgisinternal) THEN
                CREATE TRIGGER trg_player_coin_trades_immutable_v1
                BEFORE UPDATE OR DELETE ON player_coin_trades_v1
                FOR EACH ROW EXECUTE FUNCTION prevent_player_coin_trade_mutation_v1();
            END IF;
        END $$
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_mora_ledger_v1 (
            id TEXT PRIMARY KEY,
            coin_id TEXT NOT NULL REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            economy_operation_id TEXT NULL REFERENCES economic_operations(id) ON DELETE RESTRICT,
            bucket TEXT NOT NULL CHECK (bucket IN ('treasury','insurance')),
            delta NUMERIC(24,6) NOT NULL CHECK (delta <> 0),
            balance_before NUMERIC(24,6) NOT NULL CHECK (balance_before >= 0),
            balance_after NUMERIC(24,6) NOT NULL CHECK (balance_after >= 0),
            reason_code TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (balance_after = balance_before + delta)
        )
    """)
    await db.execute("""
        CREATE OR REPLACE FUNCTION prevent_player_coin_event_mutation_v1()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'player_coin_events_v1 is append-only'; END; $$
    """)
    await db.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger
                WHERE tgname='trg_player_coin_events_immutable_v1'
                AND tgrelid='player_coin_events_v1'::regclass AND NOT tgisinternal) THEN
                CREATE TRIGGER trg_player_coin_events_immutable_v1
                BEFORE UPDATE OR DELETE ON player_coin_events_v1
                FOR EACH ROW EXECUTE FUNCTION prevent_player_coin_event_mutation_v1();
            END IF;
        END $$
    """)
    await db.execute("""
        CREATE OR REPLACE FUNCTION prevent_player_coin_mora_ledger_mutation_v1()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'player_coin_mora_ledger_v1 is append-only'; END; $$
    """)
    await db.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger
                WHERE tgname='trg_player_coin_mora_ledger_immutable_v1'
                AND tgrelid='player_coin_mora_ledger_v1'::regclass AND NOT tgisinternal) THEN
                CREATE TRIGGER trg_player_coin_mora_ledger_immutable_v1
                BEFORE UPDATE OR DELETE ON player_coin_mora_ledger_v1
                FOR EACH ROW EXECUTE FUNCTION prevent_player_coin_mora_ledger_mutation_v1();
            END IF;
        END $$
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_exchange_schema_v1 (
            singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
            schema_version TEXT NOT NULL,
            installed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute(
        "INSERT INTO player_exchange_schema_v1(singleton,schema_version,installed_at) "
        "VALUES (TRUE,?,NOW()) ON CONFLICT(singleton) DO UPDATE "
        "SET schema_version=EXCLUDED.schema_version,installed_at=NOW()",
        (SCHEMA_VERSION,),
    )
    await db.commit()


async def lock_owner(db, user_id: int) -> None:
    async with db.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended('player_exchange_v1:create',0))"
    ) as cursor:
        await cursor.fetchone()
    async with db.execute("SELECT pg_advisory_xact_lock(?)", (int(user_id),)) as cursor:
        await cursor.fetchone()


async def lock_spot(db) -> None:
    async with db.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended('player_exchange_v1:spot',0))"
    ) as cursor:
        await cursor.fetchone()


async def creation_conflict(db, *, owner_id: int, name: str, ticker: str) -> str | None:
    async with db.execute(
        "SELECT CASE WHEN ticker=? THEN 'ticker' WHEN name_key=LOWER(?) THEN 'name' ELSE 'owner' END "
        "FROM player_coins_v1 WHERE "
        "((status IN ('auction','active','halted') AND owner_id=?) OR ticker=? OR name_key=LOWER(?)) LIMIT 1",
        (ticker, name, int(owner_id), ticker, name),
    ) as cursor:
        row = await cursor.fetchone()
    return str(row[0]) if row else None


async def get_creation_replay(db, *, owner_id: int, action_id: str):
    async with db.execute(
        "SELECT c.*,e.payload_json FROM player_coin_events_v1 e JOIN player_coins_v1 c ON c.id=e.coin_id "
        "WHERE e.actor_id=? AND e.action_id=? AND e.event_type='coin_created'",
        (int(owner_id), str(action_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def create_coin_rows(
    db, *, owner_id: int, name: str, ticker: str, initial_mora: int,
    rules_version: str, genesis_units: int, allocations: dict[str, int],
    economy_operation_id: str, action_id: str, auction_hours: int,
) -> dict:
    coin_id = uuid4().hex
    async with db.execute(
        "INSERT INTO player_coins_v1 "
        "(id,owner_id,name,name_key,ticker,status,rules_version,genesis_units,initial_mora,"
        "creation_operation_id,auction_ends_at) "
        "VALUES (?,?,?,LOWER(?),?,'auction',?,?,?,?,NOW()+(? * INTERVAL '1 hour')) RETURNING *",
        (coin_id, int(owner_id), name, name, ticker, rules_version, int(genesis_units),
         int(initial_mora), str(economy_operation_id), int(auction_hours)),
    ) as cursor:
        row = await cursor.fetchone()
    for kind, units in allocations.items():
        await db.execute(
            "INSERT INTO player_coin_accounts_v1 "
            "(coin_id,account_key,account_kind,user_id,available_units,reserved_units) "
            "VALUES (?,?,?,NULL,?,0)",
            (coin_id, kind, kind, int(units)),
        )
    await db.execute(
        "INSERT INTO player_coin_mora_accounts_v1(coin_id,treasury_mora,insurance_mora) VALUES (?,?,0)",
        (coin_id, int(initial_mora)),
    )
    await db.execute(
        "INSERT INTO player_coin_mora_ledger_v1 "
        "(id,coin_id,economy_operation_id,bucket,delta,balance_before,balance_after,reason_code) "
        "VALUES (?,?,?,'treasury',?,0,?,'owner_initial_liquidity')",
        (uuid4().hex, coin_id, str(economy_operation_id), int(initial_mora), int(initial_mora)),
    )
    await db.execute(
        "INSERT INTO player_coin_events_v1(id,coin_id,actor_id,event_type,action_id,payload_json) "
        "VALUES (?,?,?,'coin_created',?,?::jsonb)",
        (uuid4().hex, coin_id, int(owner_id), str(action_id), json.dumps({
            "name": name, "ticker": ticker, "initial_mora": int(initial_mora),
            "genesis_units": int(genesis_units), "allocations": allocations,
            "rules_version": rules_version, "economy_operation_id": str(economy_operation_id),
        }, sort_keys=True, separators=(",", ":"))),
    )
    return dict(row)


async def list_coins(db) -> list[dict]:
    async with db.execute(
        "SELECT id,name,ticker,status,genesis_units,circulating_units,initial_mora,"
        "auction_starts_at,auction_ends_at FROM player_coins_v1 "
        "WHERE status<>'archived' ORDER BY created_at DESC"
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def get_coin(db, coin_id: str, *, for_update: bool = False):
    suffix = " FOR UPDATE" if for_update else ""
    async with db.execute("SELECT * FROM player_coins_v1 WHERE id=?" + suffix, (coin_id,)) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def get_bid_replay(db, *, bidder_id: int, action_id: str):
    async with db.execute(
        "SELECT * FROM player_coin_auction_bids_v1 WHERE bidder_id=? AND action_id=?",
        (int(bidder_id), action_id),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def bidder_has_shared_owner_signal(db, *, bidder_id: int, owner_id: int) -> bool:
    async with db.execute(
        "SELECT COUNT(DISTINCT a.kind)=2 FROM user_login_signals a JOIN user_login_signals b "
        "ON a.kind=b.kind AND a.value_hash=b.value_hash "
        "WHERE a.user_id=? AND b.user_id=? AND a.kind IN ('ip','fp') "
        "AND a.hits>=2 AND b.hits>=2 AND a.last_seen>=NOW()-INTERVAL '30 days' "
        "AND b.last_seen>=NOW()-INTERVAL '30 days'",
        (int(bidder_id), int(owner_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return bool(row and row[0])


async def get_coin_bid_for_bidder(db, *, coin_id: str, bidder_id: int):
    async with db.execute(
        "SELECT * FROM player_coin_auction_bids_v1 WHERE coin_id=? AND bidder_id=?",
        (coin_id, int(bidder_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def insert_bid(db, *, coin_id: str, bidder_id: int, action_id: str,
                     max_price_micromora: int, escrow_mora: int, economy_operation_id: str) -> dict:
    bid_id = uuid4().hex
    async with db.execute(
        "INSERT INTO player_coin_auction_bids_v1 "
        "(id,coin_id,bidder_id,action_id,max_price_micromora,escrow_mora,economy_operation_id) "
        "VALUES (?,?,?,?,?,?,?) RETURNING *",
        (bid_id, coin_id, int(bidder_id), action_id, int(max_price_micromora),
         int(escrow_mora), economy_operation_id),
    ) as cursor:
        row = await cursor.fetchone()
    await db.execute(
        "INSERT INTO player_coin_events_v1(id,coin_id,actor_id,event_type,action_id,payload_json) "
        "VALUES (?,?,?,'auction_bid_placed',?,?::jsonb)",
        (uuid4().hex, coin_id, int(bidder_id), f"bid-placed:{action_id}", json.dumps({
            "bid_id": bid_id, "max_price_micromora": int(max_price_micromora),
            "escrow_mora": int(escrow_mora), "economy_operation_id": economy_operation_id,
        }, sort_keys=True, separators=(",", ":"))),
    )
    return dict(row)


async def list_open_bids(db, coin_id: str) -> list[dict]:
    async with db.execute(
        "SELECT * FROM player_coin_auction_bids_v1 WHERE coin_id=? AND status='open' "
        "ORDER BY created_at,id FOR UPDATE", (coin_id,),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def due_auction_ids(db, limit: int = 20) -> list[str]:
    async with db.execute(
        "SELECT id FROM player_coins_v1 WHERE status='auction' AND auction_ends_at<=NOW() "
        "ORDER BY auction_ends_at,id LIMIT ?", (int(limit),),
    ) as cursor:
        return [str(row[0]) for row in await cursor.fetchall()]


async def get_settlement(db, coin_id: str):
    async with db.execute("SELECT * FROM player_coin_auction_settlements_v1 WHERE coin_id=?", (coin_id,)) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def credit_bid_tokens(db, *, coin_id: str, bidder_id: int, units: int) -> None:
    key = f"player:{int(bidder_id)}"
    await db.execute(
        "INSERT INTO player_coin_accounts_v1 "
        "(coin_id,account_key,account_kind,user_id,available_units,reserved_units) "
        "VALUES (?,?,'player',?,?,0) ON CONFLICT(coin_id,account_key) DO UPDATE "
        "SET available_units=player_coin_accounts_v1.available_units+EXCLUDED.available_units,updated_at=NOW()",
        (coin_id, key, int(bidder_id), int(units)),
    )


async def finish_bid(db, *, bid_id: str, allocated_units: int, cost_mora, refund_operation_id: str | None) -> None:
    await db.execute(
        "UPDATE player_coin_auction_bids_v1 SET status=?,allocated_units=?,cost_mora=?,refund_operation_id=? "
        "WHERE id=? AND status='open'",
        ("won" if allocated_units else "refunded", int(allocated_units), cost_mora,
         refund_operation_id, bid_id),
    )
    async with db.execute(
        "SELECT coin_id,bidder_id,escrow_mora FROM player_coin_auction_bids_v1 WHERE id=?", (bid_id,)
    ) as cursor:
        row = await cursor.fetchone()
    await db.execute(
        "INSERT INTO player_coin_events_v1(id,coin_id,actor_id,event_type,action_id,payload_json) "
        "VALUES (?,?,?,'auction_bid_settled',?,?::jsonb)",
        (uuid4().hex, str(row[0]), int(row[1]), f"bid-settled:{bid_id}", json.dumps({
            "bid_id": bid_id, "escrow_mora": int(row[2]), "allocated_units": int(allocated_units),
            "cost_mora": str(cost_mora), "refund_operation_id": refund_operation_id,
        }, sort_keys=True, separators=(",", ":"))),
    )


async def finish_auction(db, *, coin: dict, success: bool, clearing_price: int,
                         sold_units: int, raised_mora, action_id: str) -> dict:
    coin_id = str(coin["id"])
    if success:
        await db.execute(
            "UPDATE player_coin_accounts_v1 SET available_units=available_units-? "
            "WHERE coin_id=? AND account_kind='auction' AND available_units>=?",
            (int(sold_units), coin_id, int(sold_units)),
        )
        await db.execute(
            "UPDATE player_coin_mora_accounts_v1 SET treasury_mora=treasury_mora+?,updated_at=NOW() WHERE coin_id=?",
            (raised_mora, coin_id),
        )
        if raised_mora > 0:
            await db.execute(
                "INSERT INTO player_coin_mora_ledger_v1 "
                "(id,coin_id,bucket,delta,balance_before,balance_after,reason_code) "
                "SELECT ?,?,'treasury',?,treasury_mora-?,treasury_mora,'auction_proceeds' "
                "FROM player_coin_mora_accounts_v1 WHERE coin_id=?",
                (uuid4().hex, coin_id, raised_mora, raised_mora, coin_id),
            )
        await db.execute(
            "UPDATE player_coins_v1 SET status='active',circulating_units=? WHERE id=?",
            (int(sold_units), coin_id),
        )
    else:
        await db.execute("UPDATE player_coins_v1 SET status='failed' WHERE id=?", (coin_id,))
    await db.execute(
        "INSERT INTO player_coin_auction_settlements_v1 "
        "(coin_id,success,clearing_price_micromora,sold_units,raised_mora) VALUES (?,?,?,?,?)",
        (coin_id, bool(success), int(clearing_price), int(sold_units), raised_mora),
    )
    await db.execute(
        "INSERT INTO player_coin_events_v1(id,coin_id,actor_id,event_type,action_id,payload_json) "
        "VALUES (?,?,NULL,'auction_settled',?,?::jsonb)",
        (uuid4().hex, coin_id, action_id, json.dumps({"success": bool(success),
         "clearing_price_micromora": int(clearing_price), "sold_units": int(sold_units),
         "raised_mora": str(raised_mora)}, sort_keys=True, separators=(",", ":"))),
    )
    return await get_settlement(db, coin_id)


async def release_failed_initial_liquidity(db, *, coin_id: str, amount: int, economy_operation_id: str) -> None:
    await db.execute(
        "UPDATE player_coin_mora_accounts_v1 SET treasury_mora=treasury_mora-?,updated_at=NOW() "
        "WHERE coin_id=? AND treasury_mora>=?", (int(amount), coin_id, int(amount)),
    )
    await db.execute(
        "INSERT INTO player_coin_mora_ledger_v1 "
        "(id,coin_id,economy_operation_id,bucket,delta,balance_before,balance_after,reason_code) "
        "SELECT ?,?,?,'treasury',-(?::numeric),treasury_mora+(?::numeric),treasury_mora,'failed_auction_owner_refund' "
        "FROM player_coin_mora_accounts_v1 WHERE coin_id=?",
        (uuid4().hex, coin_id, economy_operation_id, int(amount), int(amount), coin_id),
    )


async def schema_ready(db) -> bool:
    try:
        async with db.execute(
            "SELECT schema_version FROM player_exchange_schema_v1 WHERE singleton=TRUE"
        ) as cursor:
            row = await cursor.fetchone()
        return bool(row and str(row[0]) == SCHEMA_VERSION)
    except Exception:
        return False


async def lock_enabled_flag(db, key: str) -> bool:
    async with db.execute("SELECT enabled FROM system_flags WHERE key=? FOR SHARE", (key,)) as cursor:
        row = await cursor.fetchone()
    return bool(row and row[0])


async def get_order_replay(db, *, user_id: int, action_id: str):
    async with db.execute(
        "SELECT * FROM player_coin_orders_v1 WHERE user_id=? AND action_id=?",
        (int(user_id), action_id),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def get_player_coin_account(db, *, coin_id: str, user_id: int, for_update: bool = False):
    suffix = " FOR UPDATE" if for_update else ""
    async with db.execute(
        "SELECT * FROM player_coin_accounts_v1 WHERE coin_id=? AND account_key=?" + suffix,
        (coin_id, f"player:{int(user_id)}"),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def reserve_sell_units(db, *, coin_id: str, user_id: int, units: int) -> None:
    account = await get_player_coin_account(db, coin_id=coin_id, user_id=user_id, for_update=True)
    if not account or int(account["available_units"]) < int(units):
        raise ValueError("insufficient_coin_balance")
    await db.execute(
        "UPDATE player_coin_accounts_v1 SET available_units=available_units-?,"
        "reserved_units=reserved_units+?,updated_at=NOW() WHERE coin_id=? AND account_key=?",
        (int(units), int(units), coin_id, f"player:{int(user_id)}"),
    )


async def insert_order(db, *, coin_id: str, user_id: int, action_id: str, side: str,
                       time_in_force: str, price: int, units: int, reserved_mora,
                       reserve_operation_id: str | None) -> dict:
    order_id = uuid4().hex
    async with db.execute(
        "INSERT INTO player_coin_orders_v1(id,coin_id,user_id,action_id,side,time_in_force,"
        "limit_price_micromora,original_units,remaining_units,reserved_mora,reserve_operation_id) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?) RETURNING *",
        (order_id, coin_id, int(user_id), action_id, side, time_in_force, int(price),
         int(units), int(units), reserved_mora, reserve_operation_id),
    ) as cursor:
        row = await cursor.fetchone()
    await append_event(db, coin_id=coin_id, actor_id=user_id, event_type="order_placed",
                       action_id=f"order-placed:{action_id}", payload={
                           "order_id": order_id, "side": side, "time_in_force": time_in_force,
                           "price_micromora": int(price), "units": int(units),
                           "reserved_mora": str(reserved_mora),
                           "reserve_operation_id": reserve_operation_id,
                       })
    return dict(row)


async def append_event(db, *, coin_id: str, actor_id: int | None, event_type: str,
                       action_id: str, payload: dict) -> None:
    await db.execute(
        "INSERT INTO player_coin_events_v1(id,coin_id,actor_id,event_type,action_id,payload_json) "
        "VALUES(?,?,?,?,?,?::jsonb)",
        (uuid4().hex, coin_id, actor_id, event_type, action_id,
         json.dumps(payload, sort_keys=True, separators=(",", ":"))),
    )


async def get_order(db, order_id: str, *, for_update: bool = False):
    suffix = " FOR UPDATE" if for_update else ""
    async with db.execute("SELECT * FROM player_coin_orders_v1 WHERE id=?" + suffix, (order_id,)) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def best_cross(db, coin_id: str):
    async with db.execute("""
        SELECT b.id AS buy_id,s.id AS sell_id
        FROM player_coin_orders_v1 b CROSS JOIN LATERAL (
            SELECT id,limit_price_micromora,created_at FROM player_coin_orders_v1
            WHERE coin_id=? AND status='open' AND side='sell' AND remaining_units>0
            ORDER BY limit_price_micromora,created_at,id LIMIT 1 FOR UPDATE SKIP LOCKED
        ) s
        WHERE b.coin_id=? AND b.status='open' AND b.side='buy' AND b.remaining_units>0
          AND b.limit_price_micromora>=s.limit_price_micromora
        ORDER BY b.limit_price_micromora DESC,b.created_at,b.id LIMIT 1 FOR UPDATE OF b
    """, (coin_id, coin_id)) as cursor:
        row = await cursor.fetchone()
    return (str(row[0]), str(row[1])) if row else None


async def active_market_ids(db) -> list[str]:
    async with db.execute(
        "SELECT DISTINCT coin_id FROM player_coin_orders_v1 WHERE status='open' ORDER BY coin_id"
    ) as cursor:
        return [str(row[0]) for row in await cursor.fetchall()]


async def release_sell_units(db, *, coin_id: str, user_id: int, units: int) -> None:
    async with db.execute(
        "UPDATE player_coin_accounts_v1 SET reserved_units=reserved_units-?,"
        "available_units=available_units+?,updated_at=NOW() "
        "WHERE coin_id=? AND account_key=? AND reserved_units>=? RETURNING 1",
        (int(units), int(units), coin_id, f"player:{int(user_id)}", int(units)),
    ) as cursor:
        if not await cursor.fetchone():
            raise RuntimeError("Sell reserve release invariant failed.")


async def transfer_trade_tokens(db, *, coin_id: str, seller_id: int, buyer_id: int, units: int) -> None:
    async with db.execute(
        "UPDATE player_coin_accounts_v1 SET reserved_units=reserved_units-?,updated_at=NOW() "
        "WHERE coin_id=? AND account_key=? AND reserved_units>=? RETURNING 1",
        (int(units), coin_id, f"player:{int(seller_id)}", int(units)),
    ) as cursor:
        if not await cursor.fetchone():
            raise RuntimeError("Trade token reserve invariant failed.")
    await credit_bid_tokens(db, coin_id=coin_id, bidder_id=int(buyer_id), units=int(units))


async def update_order_fill(db, *, order_id: str, units: int, mora_charge=0) -> dict:
    async with db.execute(
        "UPDATE player_coin_orders_v1 SET remaining_units=remaining_units-?,"
        "reserved_mora=reserved_mora-(?::numeric),spent_mora=spent_mora+(?::numeric),"
        "status=CASE WHEN remaining_units-?=0 THEN 'filled' ELSE 'open' END,"
        "closed_at=CASE WHEN remaining_units-?=0 THEN NOW() ELSE NULL END "
        "WHERE id=? AND status='open' AND remaining_units>=? AND reserved_mora>=(?::numeric) RETURNING *",
        (int(units), mora_charge, mora_charge, int(units), int(units), order_id,
         int(units), mora_charge),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise RuntimeError("Order reserve invariant failed.")
    return dict(row)


async def close_order(db, *, order_id: str, release_operation_id: str | None) -> None:
    async with db.execute(
        "UPDATE player_coin_orders_v1 SET status='cancelled',remaining_units=0,reserved_mora=0,"
        "release_operation_id=?,closed_at=NOW() WHERE id=? AND status='open' RETURNING 1",
        (release_operation_id, order_id),
    ) as cursor:
        if not await cursor.fetchone():
            raise RuntimeError("Order close invariant failed.")


async def release_filled_buy_remainder(db, *, order_id: str, release_operation_id: str) -> None:
    async with db.execute(
        "UPDATE player_coin_orders_v1 SET reserved_mora=0,release_operation_id=? "
        "WHERE id=? AND status='filled' AND reserved_mora>0 RETURNING 1",
        (release_operation_id, order_id),
    ) as cursor:
        if not await cursor.fetchone():
            raise RuntimeError("Filled buy release invariant failed.")


async def record_trade(db, *, trade_id: str, coin_id: str, buy_order: dict, sell_order: dict,
                       units: int, price: int, gross, buyer_fee, seller_fee) -> None:
    await db.execute(
        "INSERT INTO player_coin_trades_v1(id,coin_id,buy_order_id,sell_order_id,buyer_id,seller_id,"
        "units,price_micromora,gross_mora,buyer_fee_mora,seller_fee_mora) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (trade_id, coin_id, buy_order["id"], sell_order["id"], int(buy_order["user_id"]),
         int(sell_order["user_id"]), int(units), int(price), gross, buyer_fee, seller_fee),
    )
    total_fee = buyer_fee + seller_fee
    insurance = (total_fee * 3 / 10).quantize(Decimal("0.000001"))
    burned = total_fee - insurance
    await db.execute(
        "UPDATE player_exchange_fee_fund_v1 SET insurance_mora=insurance_mora+?,burned_mora=burned_mora+? "
        "WHERE singleton=TRUE", (insurance, burned),
    )
    await append_event(db, coin_id=coin_id, actor_id=None, event_type="spot_trade",
                       action_id=f"trade:{trade_id}", payload={
                           "trade_id": trade_id, "buy_order_id": buy_order["id"],
                           "sell_order_id": sell_order["id"], "units": int(units),
                           "price_micromora": int(price), "gross_mora": str(gross),
                           "buyer_fee_mora": str(buyer_fee), "seller_fee_mora": str(seller_fee),
                       })


async def market_halt(db, coin_id: str) -> dict:
    async with db.execute(
        "SELECT halted_until,halt_reason,halt_reference_price_micromora,"
        "(halted_until IS NOT NULL AND halted_until>NOW()) AS active "
        "FROM player_coin_market_state_v1 WHERE coin_id=?", (coin_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return {"active": False, "halted_until": None, "reason": None, "reference_price_micromora": None}
    return {"halted_until": row[0], "reason": row[1],
            "reference_price_micromora": row[2], "active": bool(row[3])}


async def vwap_window(db, *, coin_id: str, minutes: int, offset_minutes: int = 0) -> dict:
    async with db.execute(
        "SELECT COALESCE(SUM(gross_mora),0),CASE WHEN COALESCE(SUM(units),0)>0 THEN "
        "ROUND(SUM(gross_mora)*(?::numeric) / (SUM(units)::numeric/(?::numeric)))::bigint ELSE NULL END "
        "FROM player_coin_trades_v1 WHERE coin_id=? "
        "AND created_at<=NOW()-((?::integer) * INTERVAL '1 minute') "
        "AND created_at>NOW()-(((?::integer)+(?::integer)) * INTERVAL '1 minute')",
        (PRICE_SCALE, TOKEN_SCALE, coin_id, int(offset_minutes), int(offset_minutes), int(minutes)),
    ) as cursor:
        row = await cursor.fetchone()
    return {"volume_mora": Decimal(row[0] or 0),
            "vwap_price_micromora": int(row[1]) if row and row[1] is not None else None}


async def set_market_halt(db, *, coin_id: str, minutes: int, reason: str, reference_price: int) -> None:
    await db.execute(
        "INSERT INTO player_coin_market_state_v1"
        "(coin_id,halted_until,halt_reason,halt_reference_price_micromora,updated_at) "
        "VALUES(?,NOW()+(? * INTERVAL '1 minute'),?,?,NOW()) "
        "ON CONFLICT(coin_id) DO UPDATE SET halted_until=GREATEST("
        "COALESCE(player_coin_market_state_v1.halted_until,NOW()),EXCLUDED.halted_until),"
        "halt_reason=EXCLUDED.halt_reason,halt_reference_price_micromora=EXCLUDED.halt_reference_price_micromora,"
        "updated_at=NOW()",
        (coin_id, int(minutes), reason, int(reference_price)),
    )
    await append_event(db, coin_id=coin_id, actor_id=None, event_type="market_halted",
                       action_id=f"market-halt:{uuid4().hex}", payload={
                           "minutes": int(minutes), "reason": reason,
                           "reference_price_micromora": int(reference_price),
                       })


async def public_order_book(db, coin_id: str, levels: int = 20) -> dict:
    level_limit = max(1, min(int(levels), 50))
    async with db.execute(
        "SELECT side,limit_price_micromora,SUM(remaining_units) AS units,COUNT(*) AS orders "
        "FROM player_coin_orders_v1 WHERE coin_id=? AND status='open' AND remaining_units>0 "
        "GROUP BY side,limit_price_micromora",
        (coin_id,),
    ) as cursor:
        rows = [dict(row) for row in await cursor.fetchall()]
    bids = sorted((r for r in rows if r["side"] == "buy"),
                  key=lambda r: int(r["limit_price_micromora"]), reverse=True)[:level_limit]
    asks = sorted((r for r in rows if r["side"] == "sell"),
                  key=lambda r: int(r["limit_price_micromora"]))[:level_limit]
    return {"bids": bids, "asks": asks}


async def public_recent_trades(db, coin_id: str, limit: int = 50) -> list[dict]:
    async with db.execute(
        "SELECT id,units,price_micromora,gross_mora,created_at FROM player_coin_trades_v1 "
        "WHERE coin_id=? ORDER BY created_at DESC,id DESC LIMIT ?",
        (coin_id, max(1, min(int(limit), 100))),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def public_market_stats(db, coin_id: str) -> dict:
    async with db.execute("""
        SELECT COUNT(*) AS trades,COALESCE(SUM(gross_mora),0) AS volume_mora,
               COALESCE(SUM(units),0) AS units,
               MIN(price_micromora) AS low_price_micromora,
               MAX(price_micromora) AS high_price_micromora,
               (ARRAY_AGG(price_micromora ORDER BY created_at DESC,id DESC))[1] AS last_price_micromora
        FROM player_coin_trades_v1 WHERE coin_id=? AND created_at>=NOW()-INTERVAL '24 hours'
    """, (coin_id,)) as cursor:
        row = await cursor.fetchone()
    result = dict(row)
    total_units = int(result.pop("units") or 0)
    result["vwap_price_micromora"] = (
        int((Decimal(result["volume_mora"]) * Decimal(PRICE_SCALE) * Decimal(TOKEN_SCALE)
             / Decimal(total_units)).quantize(Decimal("1"))) if total_units else None
    )
    result["halt"] = await market_halt(db, coin_id)
    return result
