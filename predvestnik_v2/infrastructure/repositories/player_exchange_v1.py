"""PostgreSQL persistence for player-created coins; no legacy crypto coupling."""
from __future__ import annotations

import json
from uuid import uuid4

SCHEMA_VERSION = "player-exchange-schema-v2-auction-2026-09-26"


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
