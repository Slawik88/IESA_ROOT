"""PostgreSQL persistence for player-created coins; no legacy crypto coupling."""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from core.player_exchange_shorts_v1 import pro_rata_lender_allocations
from core.player_exchange_v1 import PRICE_SCALE, TOKEN_SCALE, depth_band_bounds

SCHEMA_VERSION = "player-exchange-schema-v13-shorts-foundation-2026-10-05"


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
    await db.execute("ALTER TABLE player_coins_v1 ADD COLUMN IF NOT EXISTS total_supply_units BIGINT")
    await db.execute("ALTER TABLE player_coins_v1 ADD COLUMN IF NOT EXISTS launched_at TIMESTAMPTZ NULL")
    await db.execute("UPDATE player_coins_v1 SET total_supply_units=genesis_units WHERE total_supply_units IS NULL")
    await db.execute("ALTER TABLE player_coins_v1 ALTER COLUMN total_supply_units SET NOT NULL")
    await db.execute("ALTER TABLE player_coins_v1 DROP CONSTRAINT IF EXISTS ck_player_coin_total_supply_v1")
    await db.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_player_coin_total_supply_v2') THEN
                ALTER TABLE player_coins_v1 ADD CONSTRAINT ck_player_coin_total_supply_v2
                CHECK (total_supply_units>0 AND total_supply_units>=circulating_units);
            END IF;
        END $$
    """)
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
    await db.execute(
        "UPDATE player_coins_v1 c SET launched_at=s.settled_at "
        "FROM player_coin_auction_settlements_v1 s "
        "WHERE c.id=s.coin_id AND s.success=TRUE AND c.launched_at IS NULL"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_orders_v1 (
            id TEXT PRIMARY KEY,
            coin_id TEXT NOT NULL REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            user_id BIGINT NOT NULL REFERENCES users(user_tg_id) ON DELETE RESTRICT,
            actor_kind TEXT NOT NULL DEFAULT 'player' CHECK (actor_kind IN ('player','treasury')),
            treasury_token_bucket TEXT NULL CHECK (treasury_token_bucket IN ('treasury','market_reserve')),
            action_id TEXT NOT NULL,
            side TEXT NOT NULL CHECK (side IN ('buy','sell')),
            time_in_force TEXT NOT NULL CHECK (time_in_force IN ('gtc','ioc')),
            slippage_percent INTEGER NULL CHECK (slippage_percent IN (1,3,5)),
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
        "ALTER TABLE player_coin_orders_v1 ADD COLUMN IF NOT EXISTS slippage_percent INTEGER NULL "
        "CHECK (slippage_percent IN (1,3,5))"
    )
    await db.execute("ALTER TABLE player_coin_orders_v1 ADD COLUMN IF NOT EXISTS actor_kind TEXT NOT NULL DEFAULT 'player'")
    await db.execute(
        "ALTER TABLE player_coin_orders_v1 ADD COLUMN IF NOT EXISTS treasury_token_bucket TEXT NULL "
        "CHECK (treasury_token_bucket IN ('treasury','market_reserve'))"
    )
    await db.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_player_coin_order_actor_kind_v1') THEN
                ALTER TABLE player_coin_orders_v1 ADD CONSTRAINT ck_player_coin_order_actor_kind_v1
                CHECK (actor_kind IN ('player','treasury'));
            END IF;
        END $$
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
            buyer_kind TEXT NOT NULL DEFAULT 'player',
            seller_kind TEXT NOT NULL DEFAULT 'player',
            units BIGINT NOT NULL CHECK (units > 0),
            price_micromora BIGINT NOT NULL CHECK (price_micromora > 0),
            gross_mora NUMERIC(24,6) NOT NULL CHECK (gross_mora > 0),
            buyer_fee_mora NUMERIC(24,6) NOT NULL CHECK (buyer_fee_mora >= 0),
            seller_fee_mora NUMERIC(24,6) NOT NULL CHECK (seller_fee_mora >= 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (buyer_id <> seller_id)
        )
    """)
    await db.execute("ALTER TABLE player_coin_trades_v1 ADD COLUMN IF NOT EXISTS buyer_kind TEXT NOT NULL DEFAULT 'player'")
    await db.execute("ALTER TABLE player_coin_trades_v1 ADD COLUMN IF NOT EXISTS seller_kind TEXT NOT NULL DEFAULT 'player'")
    await db.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_player_coin_trade_actor_kinds_v1') THEN
                ALTER TABLE player_coin_trades_v1 ADD CONSTRAINT ck_player_coin_trade_actor_kinds_v1
                CHECK (buyer_kind IN ('player','treasury') AND seller_kind IN ('player','treasury'));
            END IF;
        END $$
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
            halt_public_reason TEXT NULL,
            halt_kind TEXT NULL CHECK (halt_kind IN ('automatic','manual')),
            halted_by BIGINT NULL,
            halt_reference_price_micromora BIGINT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("ALTER TABLE player_coin_market_state_v1 ADD COLUMN IF NOT EXISTS halt_public_reason TEXT NULL")
    await db.execute("ALTER TABLE player_coin_market_state_v1 ADD COLUMN IF NOT EXISTS halt_kind TEXT NULL")
    await db.execute("ALTER TABLE player_coin_market_state_v1 ADD COLUMN IF NOT EXISTS halted_by BIGINT NULL")
    await db.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_player_coin_halt_kind_v1') THEN
                ALTER TABLE player_coin_market_state_v1 ADD CONSTRAINT ck_player_coin_halt_kind_v1
                CHECK (halt_kind IN ('automatic','manual'));
            END IF;
        END $$
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_emissions_v1 (
            id TEXT PRIMARY KEY,
            coin_id TEXT NOT NULL REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            owner_id BIGINT NOT NULL REFERENCES users(user_tg_id) ON DELETE RESTRICT,
            action_id TEXT NOT NULL,
            requested_units BIGINT NOT NULL CHECK (requested_units>0),
            circulation_snapshot_units BIGINT NOT NULL CHECK (circulation_snapshot_units>0),
            projected_total_supply_units BIGINT NOT NULL CHECK (projected_total_supply_units>0),
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','cancelled','executed')),
            requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            executes_at TIMESTAMPTZ NOT NULL,
            cancel_action_id TEXT NULL,
            cancelled_at TIMESTAMPTZ NULL,
            executed_at TIMESTAMPTZ NULL,
            UNIQUE(owner_id,action_id),
            UNIQUE(owner_id,cancel_action_id)
        )
    """)
    await db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_player_coin_pending_emission_v1 "
        "ON player_coin_emissions_v1(coin_id) WHERE status='pending'"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_liquidity_withdrawals_v1 (
            id TEXT PRIMARY KEY,
            coin_id TEXT NOT NULL REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            owner_id BIGINT NOT NULL REFERENCES users(user_tg_id) ON DELETE RESTRICT,
            action_id TEXT NOT NULL,
            amount_mora NUMERIC(24,6) NOT NULL CHECK (amount_mora>0),
            treasury_snapshot_mora NUMERIC(24,6) NOT NULL CHECK (treasury_snapshot_mora>=0),
            max_amount_mora NUMERIC(24,6) NOT NULL CHECK (max_amount_mora>=amount_mora),
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','cancelled','executed')),
            requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            executes_at TIMESTAMPTZ NOT NULL,
            cancelled_at TIMESTAMPTZ NULL,
            cancel_action_id TEXT NULL,
            executed_at TIMESTAMPTZ NULL,
            economy_operation_id TEXT NULL UNIQUE REFERENCES economic_operations(id) ON DELETE RESTRICT,
            UNIQUE(owner_id,action_id)
        )
    """)
    await db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_player_coin_pending_liquidity_withdrawal_v1 "
        "ON player_coin_liquidity_withdrawals_v1(coin_id) WHERE status='pending'"
    )
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
    # Shorts stay behind their own disabled flag. These tables only preserve
    # segregated state; no balance writer or player route uses them in this wave.
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_short_reserves_v1 (
            coin_id TEXT PRIMARY KEY REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            available_mora NUMERIC(24,6) NOT NULL DEFAULT 0 CHECK (available_mora>=0),
            shorts_paused BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute(
        "INSERT INTO player_coin_short_reserves_v1(coin_id) SELECT id FROM player_coins_v1 "
        "ON CONFLICT(coin_id) DO NOTHING"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_lending_positions_v1 (
            coin_id TEXT NOT NULL REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            lender_id BIGINT NOT NULL REFERENCES users(user_tg_id) ON DELETE RESTRICT,
            available_units BIGINT NOT NULL DEFAULT 0 CHECK (available_units>=0),
            loaned_units BIGINT NOT NULL DEFAULT 0 CHECK (loaned_units>=0),
            frozen_units BIGINT NOT NULL DEFAULT 0 CHECK (frozen_units>=0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (coin_id,lender_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_short_positions_v1 (
            id TEXT PRIMARY KEY,
            coin_id TEXT NOT NULL REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            borrower_id BIGINT NOT NULL REFERENCES users(user_tg_id) ON DELETE RESTRICT,
            action_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('open','closing','closed','frozen')),
            initial_debt_units BIGINT NOT NULL CHECK (initial_debt_units>0),
            outstanding_debt_units BIGINT NOT NULL CHECK (outstanding_debt_units>=0),
            posted_collateral_mora NUMERIC(24,6) NOT NULL CHECK (posted_collateral_mora>=0),
            locked_sale_proceeds_mora NUMERIC(24,6) NOT NULL CHECK (locked_sale_proceeds_mora>=0),
            accrued_interest_mora NUMERIC(24,6) NOT NULL DEFAULT 0 CHECK (accrued_interest_mora>=0),
            opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            closed_at TIMESTAMPTZ NULL,
            UNIQUE (borrower_id,action_id),
            UNIQUE (id,coin_id),
            CHECK (outstanding_debt_units<=initial_debt_units),
            CHECK ((status IN ('open','closing') AND outstanding_debt_units>0 AND closed_at IS NULL) OR
                   (status IN ('closed','frozen') AND outstanding_debt_units=0 AND closed_at IS NOT NULL))
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_short_loans_v1 (
            id TEXT PRIMARY KEY,
            coin_id TEXT NOT NULL REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            position_id TEXT NOT NULL REFERENCES player_coin_short_positions_v1(id) ON DELETE RESTRICT,
            lender_id BIGINT NOT NULL REFERENCES users(user_tg_id) ON DELETE RESTRICT,
            principal_units BIGINT NOT NULL CHECK (principal_units>0),
            outstanding_units BIGINT NOT NULL CHECK (outstanding_units>=0),
            repaid_units BIGINT NOT NULL DEFAULT 0 CHECK (repaid_units>=0),
            frozen_units BIGINT NOT NULL DEFAULT 0 CHECK (frozen_units>=0),
            opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            closed_at TIMESTAMPTZ NULL,
            UNIQUE (position_id,lender_id),
            UNIQUE (id,coin_id,position_id,lender_id),
            FOREIGN KEY (position_id,coin_id) REFERENCES player_coin_short_positions_v1(id,coin_id) ON DELETE RESTRICT,
            CHECK (principal_units=outstanding_units+repaid_units+frozen_units)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_short_frozen_claims_v1 (
            id TEXT PRIMARY KEY,
            coin_id TEXT NOT NULL REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            position_id TEXT NOT NULL,
            loan_id TEXT NOT NULL UNIQUE,
            lender_id BIGINT NOT NULL REFERENCES users(user_tg_id) ON DELETE RESTRICT,
            principal_units BIGINT NOT NULL CHECK (principal_units>0),
            remaining_units BIGINT NOT NULL CHECK (remaining_units>=0 AND remaining_units<=principal_units),
            status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','settled')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            settled_at TIMESTAMPTZ NULL,
            FOREIGN KEY (position_id,coin_id) REFERENCES player_coin_short_positions_v1(id,coin_id) ON DELETE RESTRICT,
            FOREIGN KEY (loan_id,coin_id,position_id,lender_id)
                REFERENCES player_coin_short_loans_v1(id,coin_id,position_id,lender_id) ON DELETE RESTRICT,
            CHECK ((status='open' AND remaining_units>0 AND settled_at IS NULL) OR
                   (status='settled' AND remaining_units=0 AND settled_at IS NOT NULL))
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_short_reserve_ledger_v1 (
            id TEXT PRIMARY KEY,
            coin_id TEXT NOT NULL REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            source_type TEXT NOT NULL CHECK (source_type IN ('spot_fee','liquidation_penalty','claim_buyback')),
            source_id TEXT NOT NULL,
            buyback_cycle_hour TIMESTAMPTZ NULL,
            delta_mora NUMERIC(24,6) NOT NULL CHECK (delta_mora<>0),
            balance_before NUMERIC(24,6) NOT NULL CHECK (balance_before>=0),
            balance_after NUMERIC(24,6) NOT NULL CHECK (balance_after>=0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (source_type,source_id),
            CHECK (balance_after=balance_before+delta_mora)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_short_buyback_cycles_v1 (
            coin_id TEXT NOT NULL REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            cycle_hour TIMESTAMPTZ NOT NULL,
            reserve_snapshot_mora NUMERIC(24,6) NOT NULL CHECK (reserve_snapshot_mora>=0),
            budget_mora NUMERIC(24,6) NOT NULL CHECK (budget_mora>=0),
            spent_mora NUMERIC(24,6) NOT NULL DEFAULT 0 CHECK (spent_mora>=0),
            action_id TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (coin_id,cycle_hour),
            CHECK (cycle_hour=date_trunc('hour',cycle_hour)),
            CHECK (budget_mora=reserve_snapshot_mora*5/100),
            CHECK (spent_mora<=budget_mora)
        )
    """)
    await db.execute(
        "ALTER TABLE player_coin_short_reserve_ledger_v1 ADD COLUMN IF NOT EXISTS buyback_cycle_hour TIMESTAMPTZ NULL"
    )
    await db.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_short_reserve_ledger_cycle_v1') THEN
                ALTER TABLE player_coin_short_reserve_ledger_v1
                ADD CONSTRAINT fk_short_reserve_ledger_cycle_v1
                FOREIGN KEY (coin_id,buyback_cycle_hour)
                REFERENCES player_coin_short_buyback_cycles_v1(coin_id,cycle_hour) ON DELETE RESTRICT;
            END IF;
        END $$
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_coin_short_events_v1 (
            id TEXT PRIMARY KEY,
            coin_id TEXT NOT NULL REFERENCES player_coins_v1(id) ON DELETE RESTRICT,
            actor_id BIGINT NULL REFERENCES users(user_tg_id) ON DELETE RESTRICT,
            event_type TEXT NOT NULL,
            action_id TEXT NOT NULL,
            payload_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (action_id)
        )
    """)
    await db.execute("""
        CREATE OR REPLACE FUNCTION sync_player_coin_short_pause_v1()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE affected_coin TEXT;
        BEGIN
            affected_coin := COALESCE(NEW.coin_id,OLD.coin_id);
            IF TG_OP <> 'DELETE' AND NEW.status='open' THEN
                UPDATE player_coin_short_reserves_v1 SET shorts_paused=TRUE,updated_at=NOW()
                WHERE coin_id=affected_coin;
            ELSIF NOT EXISTS (SELECT 1 FROM player_coin_short_frozen_claims_v1
                              WHERE coin_id=affected_coin AND status='open') THEN
                UPDATE player_coin_short_reserves_v1 SET shorts_paused=FALSE,updated_at=NOW()
                WHERE coin_id=affected_coin;
            END IF;
            RETURN NULL;
        END $$
    """)
    await db.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger
                WHERE tgname='trg_player_coin_short_pause_v1'
                AND tgrelid='player_coin_short_frozen_claims_v1'::regclass AND NOT tgisinternal) THEN
                CREATE TRIGGER trg_player_coin_short_pause_v1
                AFTER INSERT OR UPDATE OR DELETE ON player_coin_short_frozen_claims_v1
                FOR EACH ROW EXECUTE FUNCTION sync_player_coin_short_pause_v1();
            END IF;
        END $$
    """)
    await db.execute("""
        CREATE OR REPLACE FUNCTION assert_player_coin_short_reconciliation_v1()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE affected_coin TEXT; affected_lender BIGINT; affected_position TEXT;
        DECLARE want_loaned BIGINT; want_frozen BIGINT; actual_loaned BIGINT; actual_frozen BIGINT;
        DECLARE want_debt BIGINT; actual_debt BIGINT;
        DECLARE payload_new JSONB; payload_old JSONB;
        BEGIN
            payload_new := to_jsonb(NEW);
            payload_old := to_jsonb(OLD);
            affected_coin := COALESCE(payload_new->>'coin_id',payload_old->>'coin_id');
            affected_lender := COALESCE(payload_new->>'lender_id',payload_old->>'lender_id')::BIGINT;
            IF TG_TABLE_NAME='player_coin_short_positions_v1' THEN
                affected_position := COALESCE(payload_new->>'id',payload_old->>'id');
            ELSE
                affected_position := COALESCE(payload_new->>'position_id',payload_old->>'position_id');
            END IF;
            SELECT COALESCE(SUM(outstanding_units),0),COALESCE(SUM(frozen_units),0)
              INTO want_loaned,want_frozen FROM player_coin_short_loans_v1
              WHERE coin_id=affected_coin AND lender_id=affected_lender;
            SELECT loaned_units,frozen_units INTO actual_loaned,actual_frozen
              FROM player_coin_lending_positions_v1
              WHERE coin_id=affected_coin AND lender_id=affected_lender;
            IF actual_loaned IS NOT NULL AND (actual_loaned<>want_loaned OR actual_frozen<>want_frozen) THEN
                RAISE EXCEPTION 'player_coin_short lending totals are inconsistent';
            END IF;
            SELECT COALESCE(SUM(outstanding_units),0) INTO want_debt
              FROM player_coin_short_loans_v1 WHERE position_id=affected_position AND coin_id=affected_coin;
            SELECT outstanding_debt_units INTO actual_debt FROM player_coin_short_positions_v1
              WHERE id=affected_position AND coin_id=affected_coin;
            IF actual_debt IS NOT NULL AND actual_debt<>want_debt THEN
                RAISE EXCEPTION 'player_coin_short position debt is inconsistent';
            END IF;
            RETURN NULL;
        END $$
    """)
    await db.execute("""
        DO $$ DECLARE rel TEXT; BEGIN
            FOREACH rel IN ARRAY ARRAY['player_coin_lending_positions_v1','player_coin_short_positions_v1',
                                       'player_coin_short_loans_v1','player_coin_short_frozen_claims_v1'] LOOP
                IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='trg_short_reconcile_' || rel
                               AND tgrelid=rel::regclass AND NOT tgisinternal) THEN
                    EXECUTE format('CREATE CONSTRAINT TRIGGER %I AFTER INSERT OR UPDATE OR DELETE ON %I '
                                   || 'DEFERRABLE INITIALLY DEFERRED FOR EACH ROW '
                                   || 'EXECUTE FUNCTION assert_player_coin_short_reconciliation_v1()',
                                   'trg_short_reconcile_' || rel, rel);
                END IF;
            END LOOP;
        END $$
    """)
    await db.execute("""
        CREATE OR REPLACE FUNCTION prevent_player_coin_short_event_mutation_v1()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'player_coin_short_events_v1 is append-only'; END; $$
    """)
    await db.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger
                WHERE tgname='trg_player_coin_short_events_immutable_v1'
                AND tgrelid='player_coin_short_events_v1'::regclass AND NOT tgisinternal) THEN
                CREATE TRIGGER trg_player_coin_short_events_immutable_v1
                BEFORE UPDATE OR DELETE ON player_coin_short_events_v1
                FOR EACH ROW EXECUTE FUNCTION prevent_player_coin_short_event_mutation_v1();
            END IF;
        END $$
    """)
    await db.execute("""
        CREATE OR REPLACE FUNCTION prevent_player_coin_short_reserve_ledger_mutation_v1()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'player_coin_short_reserve_ledger_v1 is append-only'; END; $$
    """)
    await db.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger
                WHERE tgname='trg_player_coin_short_reserve_ledger_immutable_v1'
                AND tgrelid='player_coin_short_reserve_ledger_v1'::regclass AND NOT tgisinternal) THEN
                CREATE TRIGGER trg_player_coin_short_reserve_ledger_immutable_v1
                BEFORE UPDATE OR DELETE ON player_coin_short_reserve_ledger_v1
                FOR EACH ROW EXECUTE FUNCTION prevent_player_coin_short_reserve_ledger_mutation_v1();
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
        "(id,owner_id,name,name_key,ticker,status,rules_version,genesis_units,total_supply_units,initial_mora,"
        "creation_operation_id,auction_ends_at) "
        "VALUES (?,?,?,LOWER(?),?,'auction',?,?,?,?,?,NOW()+(? * INTERVAL '1 hour')) RETURNING *",
        (coin_id, int(owner_id), name, name, ticker, rules_version, int(genesis_units),
         int(genesis_units), int(initial_mora), str(economy_operation_id), int(auction_hours)),
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
        "INSERT INTO player_coin_short_reserves_v1(coin_id) VALUES(?) ON CONFLICT(coin_id) DO NOTHING",
        (coin_id,),
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
        "SELECT id,name,ticker,status,genesis_units,total_supply_units,circulating_units,initial_mora,"
        "auction_starts_at,auction_ends_at FROM player_coins_v1 "
        "WHERE status<>'archived' ORDER BY created_at DESC"
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def player_recovery_state(
    db, *, user_id: int, limit: int = 50, holdings_cursor=None, orders_cursor=None,
    bids_cursor=None, coins_cursor=None,
) -> dict:
    row_limit = max(1, min(int(limit), 100)) + 1
    hc_time, hc_id = holdings_cursor or (None, None)
    async with db.execute(
        "SELECT c.id AS coin_id,c.name,c.ticker,c.status,a.available_units,a.reserved_units,c.created_at "
        "FROM player_coin_accounts_v1 a JOIN player_coins_v1 c ON c.id=a.coin_id "
        "WHERE a.account_kind='player' AND a.user_id=? "
        "AND (a.available_units>0 OR a.reserved_units>0) "
        "AND (?::text IS NULL OR (c.created_at,c.id)<((?::text)::timestamptz,?)) "
        "ORDER BY c.created_at DESC,c.id DESC LIMIT ?",
        (int(user_id), hc_time, hc_time, hc_id, row_limit),
    ) as cursor:
        holdings = [dict(row) for row in await cursor.fetchall()]
    oc_rank, oc_time, oc_id = orders_cursor or (None, None, None)
    async with db.execute(
        "SELECT o.id,o.coin_id,c.name,c.ticker,o.actor_kind,o.treasury_token_bucket,"
        "o.side,o.time_in_force,o.slippage_percent,"
        "o.limit_price_micromora,o.original_units,o.remaining_units,o.reserved_mora,o.spent_mora,"
        "o.status,o.created_at,o.closed_at FROM player_coin_orders_v1 o "
        "JOIN player_coins_v1 c ON c.id=o.coin_id WHERE o.user_id=? "
        "AND (?::integer IS NULL OR (CASE WHEN o.status='open' THEN 1 ELSE 0 END,o.created_at,o.id)"
        "<(?::integer,(?::text)::timestamptz,?)) "
        "ORDER BY (o.status='open') DESC,o.created_at DESC,o.id DESC LIMIT ?",
        (int(user_id), oc_rank, oc_rank, oc_time, oc_id, row_limit),
    ) as cursor:
        orders = [dict(row) for row in await cursor.fetchall()]
    bc_rank, bc_time, bc_id = bids_cursor or (None, None, None)
    async with db.execute(
        "SELECT b.id,b.coin_id,c.name,c.ticker,b.max_price_micromora,b.escrow_mora,b.status,"
        "b.allocated_units,b.cost_mora,b.created_at,c.auction_ends_at "
        "FROM player_coin_auction_bids_v1 b JOIN player_coins_v1 c ON c.id=b.coin_id "
        "WHERE b.bidder_id=? AND (?::integer IS NULL OR "
        "(CASE WHEN b.status='open' THEN 1 ELSE 0 END,b.created_at,b.id)<(?::integer,(?::text)::timestamptz,?)) "
        "ORDER BY (b.status='open') DESC,b.created_at DESC,b.id DESC LIMIT ?",
        (int(user_id), bc_rank, bc_rank, bc_time, bc_id, row_limit),
    ) as cursor:
        bids = [dict(row) for row in await cursor.fetchall()]
    cc_time, cc_id = coins_cursor or (None, None)
    async with db.execute(
        "SELECT c.id AS coin_id,c.name,c.ticker,c.status,c.auction_ends_at,c.created_at,"
        "e.id AS pending_emission_id,e.requested_units AS pending_emission_units,"
        "e.circulation_snapshot_units AS emission_circulation_snapshot_units,"
        "e.projected_total_supply_units AS emission_projected_total_supply_units,"
        "e.reason AS pending_emission_reason,e.requested_at AS emission_requested_at,"
        "e.executes_at AS emission_executes_at,"
        "COALESCE(e.executes_at>NOW()+INTERVAL '1 hour',FALSE) AS emission_can_cancel,"
        "w.id AS pending_liquidity_withdrawal_id,w.amount_mora AS pending_liquidity_withdrawal_mora,"
        "w.requested_at AS liquidity_withdrawal_requested_at,w.executes_at AS liquidity_withdrawal_executes_at,"
        "COALESCE(w.status='pending',FALSE) AS liquidity_withdrawal_can_cancel "
        "FROM player_coins_v1 c "
        "LEFT JOIN player_coin_emissions_v1 e ON e.coin_id=c.id AND e.status='pending' "
        "LEFT JOIN player_coin_liquidity_withdrawals_v1 w ON w.coin_id=c.id AND w.status='pending' "
        "WHERE c.owner_id=? AND (?::text IS NULL OR (c.created_at,c.id)<((?::text)::timestamptz,?)) "
        "ORDER BY c.created_at DESC,c.id DESC LIMIT ?",
        (int(user_id), cc_time, cc_time, cc_id, row_limit),
    ) as cursor:
        owned_coins = [dict(row) for row in await cursor.fetchall()]
    return {"holdings": holdings, "orders": orders, "auction_bids": bids,
            "owned_coins": owned_coins}


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
            "UPDATE player_coins_v1 SET status='active',circulating_units=?,launched_at=NOW() WHERE id=?",
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


async def create_treasury_ladder(
    db, *, coin: dict, clearing_price: int, buy_levels: list[tuple[int, int, Decimal]],
    sell_levels: list[tuple[int, int]],
) -> None:
    coin_id = str(coin["id"])
    owner_id = int(coin["owner_id"])
    total_buy = sum((row[2] for row in buy_levels), Decimal("0"))
    total_sell = sum(row[1] for row in sell_levels)
    if total_buy:
        async with db.execute(
            "UPDATE player_coin_mora_accounts_v1 SET treasury_mora=treasury_mora-(?::numeric),updated_at=NOW() "
            "WHERE coin_id=? AND treasury_mora>=(?::numeric) RETURNING treasury_mora",
            (total_buy, coin_id, total_buy),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise RuntimeError("Treasury Mora ladder reserve invariant failed.")
        await db.execute(
            "INSERT INTO player_coin_mora_ledger_v1(id,coin_id,bucket,delta,balance_before,balance_after,reason_code) "
            "VALUES(?,?,'treasury',-(?::numeric),(?::numeric)+(?::numeric),?,'launch_ladder_reserve')",
            (uuid4().hex, coin_id, total_buy, row[0], total_buy, row[0]),
        )
    if total_sell:
        async with db.execute(
            "UPDATE player_coin_accounts_v1 SET available_units=available_units-?,reserved_units=reserved_units+?,updated_at=NOW() "
            "WHERE coin_id=? AND account_kind='market_reserve' AND available_units>=? RETURNING 1",
            (total_sell, total_sell, coin_id, total_sell),
        ) as cursor:
            if not await cursor.fetchone():
                raise RuntimeError("Treasury token ladder reserve invariant failed.")
    for index, (price, units, reserve) in enumerate(buy_levels, 1):
        await insert_order(
            db, coin_id=coin_id, user_id=owner_id, action_id=f"treasury-ladder-buy-{coin_id}-{index}",
            side="buy", time_in_force="gtc", price=price, units=units, reserved_mora=reserve,
            reserve_operation_id=None, actor_kind="treasury",
        )
    for index, (price, units) in enumerate(sell_levels, 1):
        await insert_order(
            db, coin_id=coin_id, user_id=owner_id, action_id=f"treasury-ladder-sell-{coin_id}-{index}",
            side="sell", time_in_force="gtc", price=price, units=units, reserved_mora=Decimal("0"),
            reserve_operation_id=None, actor_kind="treasury", treasury_token_bucket="market_reserve",
        )
    await append_event(
        db, coin_id=coin_id, actor_id=None, event_type="treasury_ladder_created",
        action_id=f"treasury-ladder:{coin_id}", payload={
            "clearing_price_micromora": int(clearing_price), "buy_levels": len(buy_levels),
            "sell_levels": len(sell_levels), "reserved_mora": str(total_buy), "reserved_units": total_sell,
        },
    )


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


async def get_lending_position(db, *, coin_id: str, lender_id: int, for_update: bool = False):
    suffix = " FOR UPDATE" if for_update else ""
    async with db.execute(
        "SELECT * FROM player_coin_lending_positions_v1 WHERE coin_id=? AND lender_id=?" + suffix,
        (str(coin_id), int(lender_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def allocate_lending_units(db, *, coin_id: str, position_id: str, units: int) -> list[dict]:
    """Allocate one loan from free lender balances under the shared Spot lock."""
    async with db.execute(
        "SELECT lender_id,available_units FROM player_coin_lending_positions_v1 "
        "WHERE coin_id=? AND available_units>0 ORDER BY created_at,lender_id FOR UPDATE",
        (str(coin_id),),
    ) as cursor:
        lenders = [dict(row) for row in await cursor.fetchall()]
    allocations = pro_rata_lender_allocations(
        requested_units=int(units),
        lenders=[(int(row["lender_id"]), int(row["available_units"])) for row in lenders],
    )
    records = []
    for lender_id, allocated_units in allocations:
        await db.execute(
            "UPDATE player_coin_lending_positions_v1 SET available_units=available_units-?,"
            "loaned_units=loaned_units+?,updated_at=NOW() WHERE coin_id=? AND lender_id=? "
            "AND available_units>=?",
            (int(allocated_units), int(allocated_units), str(coin_id), int(lender_id), int(allocated_units)),
        )
        loan_id = uuid4().hex
        async with db.execute(
            "INSERT INTO player_coin_short_loans_v1"
            "(id,coin_id,position_id,lender_id,principal_units,outstanding_units) "
            "VALUES(?,?,?,?,?,?) RETURNING *",
            (loan_id, str(coin_id), str(position_id), int(lender_id), int(allocated_units), int(allocated_units)),
        ) as cursor:
            records.append(dict(await cursor.fetchone()))
    if sum(int(row["principal_units"]) for row in records) != int(units):
        raise RuntimeError("Short loan allocation invariant failed.")
    return records


async def move_player_units_to_lending(db, *, coin_id: str, lender_id: int, units: int) -> dict:
    account = await get_player_coin_account(db, coin_id=coin_id, user_id=lender_id, for_update=True)
    if not account or int(account["available_units"]) < int(units):
        raise ValueError("insufficient_coin_balance")
    await db.execute(
        "UPDATE player_coin_accounts_v1 SET available_units=available_units-?,updated_at=NOW() "
        "WHERE coin_id=? AND account_key=?",
        (int(units), str(coin_id), f"player:{int(lender_id)}"),
    )
    await db.execute(
        "INSERT INTO player_coin_lending_positions_v1(coin_id,lender_id,available_units) VALUES(?,?,?) "
        "ON CONFLICT(coin_id,lender_id) DO UPDATE SET available_units="
        "player_coin_lending_positions_v1.available_units+EXCLUDED.available_units,updated_at=NOW()",
        (str(coin_id), int(lender_id), int(units)),
    )
    return await get_lending_position(db, coin_id=coin_id, lender_id=lender_id, for_update=True)


async def move_lending_units_to_player(db, *, coin_id: str, lender_id: int, units: int) -> dict:
    position = await get_lending_position(db, coin_id=coin_id, lender_id=lender_id, for_update=True)
    if not position or int(position["available_units"]) < int(units):
        raise ValueError("insufficient_lending_available")
    await db.execute(
        "UPDATE player_coin_lending_positions_v1 SET available_units=available_units-?,updated_at=NOW() "
        "WHERE coin_id=? AND lender_id=?",
        (int(units), str(coin_id), int(lender_id)),
    )
    await credit_bid_tokens(db, coin_id=str(coin_id), bidder_id=int(lender_id), units=int(units))
    return await get_lending_position(db, coin_id=coin_id, lender_id=lender_id, for_update=True)


async def get_short_event_by_action(db, *, action_id: str):
    async with db.execute(
        "SELECT * FROM player_coin_short_events_v1 WHERE action_id=?", (str(action_id),)
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def append_short_event(db, *, coin_id: str, actor_id: int | None, event_type: str,
                             action_id: str, payload: dict) -> None:
    await db.execute(
        "INSERT INTO player_coin_short_events_v1(id,coin_id,actor_id,event_type,action_id,payload_json) "
        "VALUES(?,?,?,?,?,?::jsonb)",
        (uuid4().hex, str(coin_id), actor_id, str(event_type), str(action_id),
         json.dumps(payload, sort_keys=True, separators=(",", ":"))),
    )


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
                       reserve_operation_id: str | None, slippage_percent: int | None = None,
                       actor_kind: str = "player", treasury_token_bucket: str | None = None) -> dict:
    order_id = uuid4().hex
    async with db.execute(
        "INSERT INTO player_coin_orders_v1(id,coin_id,user_id,actor_kind,treasury_token_bucket,action_id,side,time_in_force,slippage_percent,"
        "limit_price_micromora,original_units,remaining_units,reserved_mora,reserve_operation_id) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING *",
        (order_id, coin_id, int(user_id), actor_kind, treasury_token_bucket, action_id, side, time_in_force, slippage_percent, int(price),
         int(units), int(units), reserved_mora, reserve_operation_id),
    ) as cursor:
        row = await cursor.fetchone()
    await append_event(db, coin_id=coin_id, actor_id=user_id, event_type="order_placed",
                       action_id=f"order-placed:{action_id}", payload={
                           "order_id": order_id, "actor_kind": actor_kind,
                           "treasury_token_bucket": treasury_token_bucket,
                           "side": side, "time_in_force": time_in_force,
                           "slippage_percent": slippage_percent,
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


async def get_event_by_action(db, *, actor_id: int, action_id: str):
    async with db.execute(
        "SELECT * FROM player_coin_events_v1 WHERE actor_id=? AND action_id=?",
        (int(actor_id), action_id),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


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


async def treasury_has_crossing_opposite_order(db, *, coin_id: str, side: str, price: int) -> bool:
    """Return whether a new treasury order would cross its own open liquidity."""
    opposite_side = "sell" if side == "buy" else "buy"
    comparator = "<=" if side == "buy" else ">="
    async with db.execute(
        "SELECT EXISTS(SELECT 1 FROM player_coin_orders_v1 "
        "WHERE coin_id=? AND actor_kind='treasury' AND side=? AND status='open' "
        f"AND remaining_units>0 AND limit_price_micromora{comparator}?)",
        (str(coin_id), opposite_side, int(price)),
    ) as cursor:
        row = await cursor.fetchone()
    return bool(row[0])


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


async def transfer_trade_tokens(db, *, coin_id: str, sell_order: dict, buy_order: dict, units: int) -> None:
    seller_key = (
        str(sell_order.get("treasury_token_bucket") or "market_reserve")
        if sell_order.get("actor_kind") == "treasury" else f"player:{int(sell_order['user_id'])}"
    )
    async with db.execute(
        "UPDATE player_coin_accounts_v1 SET reserved_units=reserved_units-?,updated_at=NOW() "
        "WHERE coin_id=? AND account_key=? AND reserved_units>=? RETURNING 1",
        (int(units), coin_id, seller_key, int(units)),
    ) as cursor:
        if not await cursor.fetchone():
            raise RuntimeError("Trade token reserve invariant failed.")
    if buy_order.get("actor_kind") == "treasury":
        async with db.execute(
            "UPDATE player_coin_accounts_v1 SET available_units=available_units+?,updated_at=NOW() "
            "WHERE coin_id=? AND account_kind='treasury' RETURNING 1", (int(units), coin_id),
        ) as cursor:
            if not await cursor.fetchone():
                raise RuntimeError("Treasury token credit invariant failed.")
    else:
        await credit_bid_tokens(db, coin_id=coin_id, bidder_id=int(buy_order["user_id"]), units=int(units))
    circulation_delta = (
        int(units) if sell_order.get("actor_kind") == "treasury"
        else -int(units) if buy_order.get("actor_kind") == "treasury" else 0
    )
    if circulation_delta:
        async with db.execute(
            "UPDATE player_coins_v1 SET circulating_units=circulating_units+? "
            "WHERE id=? AND circulating_units+?>=0 RETURNING 1",
            (circulation_delta, coin_id, circulation_delta),
        ) as cursor:
            if not await cursor.fetchone():
                raise RuntimeError("Coin circulation invariant failed.")


async def credit_treasury_mora(
    db, *, coin_id: str, amount, reason: str, economy_operation_id: str | None = None,
) -> None:
    async with db.execute(
        "UPDATE player_coin_mora_accounts_v1 SET treasury_mora=treasury_mora+(?::numeric),updated_at=NOW() "
        "WHERE coin_id=? RETURNING 1",
        (amount, coin_id),
    ) as cursor:
        if not await cursor.fetchone():
            raise RuntimeError("Treasury Mora credit invariant failed.")
    await db.execute(
        "INSERT INTO player_coin_mora_ledger_v1"
        "(id,coin_id,economy_operation_id,bucket,delta,balance_before,balance_after,reason_code) "
        "SELECT ?,?,?,'treasury',?,treasury_mora-?,treasury_mora,? "
        "FROM player_coin_mora_accounts_v1 WHERE coin_id=?",
        (uuid4().hex, coin_id, economy_operation_id, amount, amount, reason, coin_id),
    )


async def reserve_treasury_mora(db, *, coin_id: str, amount, reason: str) -> None:
    async with db.execute(
        "UPDATE player_coin_mora_accounts_v1 SET treasury_mora=treasury_mora-(?::numeric),updated_at=NOW() "
        "WHERE coin_id=? AND treasury_mora>=(?::numeric) RETURNING treasury_mora",
        (amount, str(coin_id), amount),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise ValueError("insufficient_treasury_mora")
    await db.execute(
        "INSERT INTO player_coin_mora_ledger_v1(id,coin_id,bucket,delta,balance_before,balance_after,reason_code) "
        "VALUES(?,?,'treasury',-(?::numeric),(?::numeric)+(?::numeric),?,?)",
        (uuid4().hex, str(coin_id), amount, row[0], amount, row[0], reason),
    )


async def withdraw_treasury_mora(
    db, *, coin_id: str, amount, reason: str, economy_operation_id: str,
) -> None:
    async with db.execute(
        "UPDATE player_coin_mora_accounts_v1 SET treasury_mora=treasury_mora-(?::numeric),updated_at=NOW() "
        "WHERE coin_id=? AND treasury_mora>=(?::numeric) RETURNING treasury_mora",
        (amount, str(coin_id), amount),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise ValueError("insufficient_treasury_mora")
    await db.execute(
        "INSERT INTO player_coin_mora_ledger_v1"
        "(id,coin_id,economy_operation_id,bucket,delta,balance_before,balance_after,reason_code) "
        "VALUES(?,?,?,'treasury',-(?::numeric),(?::numeric)+(?::numeric),?,?)",
        (uuid4().hex, str(coin_id), str(economy_operation_id), amount, row[0], amount, row[0], reason),
    )


async def reserve_treasury_tokens(db, *, coin_id: str, units: int, bucket: str = "treasury") -> None:
    if bucket not in {"treasury", "market_reserve"}:
        raise ValueError("invalid_treasury_bucket")
    async with db.execute(
        "UPDATE player_coin_accounts_v1 SET available_units=available_units-?,"
        "reserved_units=reserved_units+?,updated_at=NOW() "
        "WHERE coin_id=? AND account_kind=? AND available_units>=? RETURNING 1",
        (int(units), int(units), str(coin_id), bucket, int(units)),
    ) as cursor:
        if not await cursor.fetchone():
            raise ValueError("insufficient_treasury_tokens")


async def burn_treasury_tokens(db, *, coin_id: str, units: int) -> None:
    async with db.execute(
        "UPDATE player_coin_accounts_v1 SET available_units=available_units-?,updated_at=NOW() "
        "WHERE coin_id=? AND account_kind='treasury' AND available_units>=? RETURNING 1",
        (int(units), str(coin_id), int(units)),
    ) as cursor:
        if not await cursor.fetchone():
            raise ValueError("insufficient_treasury_tokens")
    async with db.execute(
        "UPDATE player_coins_v1 SET total_supply_units=total_supply_units-? "
        "WHERE id=? AND total_supply_units-circulating_units>=? RETURNING 1",
        (int(units), str(coin_id), int(units)),
    ) as cursor:
        if not await cursor.fetchone():
            raise ValueError("cannot_burn_below_genesis")


async def release_treasury_order(db, *, order: dict, reason: str, filled: bool = False) -> None:
    if order["side"] == "buy" and Decimal(order["reserved_mora"]) > 0:
        await credit_treasury_mora(
            db, coin_id=str(order["coin_id"]), amount=Decimal(order["reserved_mora"]),
            reason="treasury_order_release",
        )
    elif order["side"] == "sell" and int(order["remaining_units"]) > 0:
        bucket = str(order.get("treasury_token_bucket") or "market_reserve")
        async with db.execute(
            "UPDATE player_coin_accounts_v1 SET reserved_units=reserved_units-?,available_units=available_units+?,updated_at=NOW() "
            "WHERE coin_id=? AND account_kind=? AND reserved_units>=? RETURNING 1",
            (int(order["remaining_units"]), int(order["remaining_units"]), str(order["coin_id"]), bucket,
             int(order["remaining_units"])),
        ) as cursor:
            if not await cursor.fetchone():
                raise RuntimeError("Treasury sell release invariant failed.")
    if filled:
        await db.execute("UPDATE player_coin_orders_v1 SET reserved_mora=0 WHERE id=?", (str(order["id"]),))


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


async def credit_short_reserve(db, *, coin_id: str, amount: Decimal, source_type: str,
                              source_id: str, buyback_cycle_hour=None) -> None:
    """Append one segregated, non-negative Shorts reserve receipt under the Spot lock."""
    if Decimal(amount) <= 0:
        return
    async with db.execute(
        "SELECT available_mora FROM player_coin_short_reserves_v1 WHERE coin_id=? FOR UPDATE", (str(coin_id),)
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise RuntimeError("Shorts reserve is missing for coin.")
    before = Decimal(row[0])
    after = before + Decimal(amount)
    await db.execute(
        "UPDATE player_coin_short_reserves_v1 SET available_mora=?,updated_at=NOW() WHERE coin_id=?",
        (after, str(coin_id)),
    )
    await db.execute(
        "INSERT INTO player_coin_short_reserve_ledger_v1"
        "(id,coin_id,source_type,source_id,buyback_cycle_hour,delta_mora,balance_before,balance_after) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (uuid4().hex, str(coin_id), str(source_type), str(source_id), buyback_cycle_hour,
         Decimal(amount), before, after),
    )


async def record_trade(db, *, trade_id: str, coin_id: str, buy_order: dict, sell_order: dict,
                       units: int, price: int, gross, buyer_fee, seller_fee,
                       shorts_reserve_enabled: bool = False) -> None:
    await db.execute(
        "INSERT INTO player_coin_trades_v1(id,coin_id,buy_order_id,sell_order_id,buyer_id,seller_id,"
        "units,price_micromora,gross_mora,buyer_fee_mora,seller_fee_mora,buyer_kind,seller_kind) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (trade_id, coin_id, buy_order["id"], sell_order["id"], int(buy_order["user_id"]),
         int(sell_order["user_id"]), int(units), int(price), gross, buyer_fee, seller_fee,
         buy_order.get("actor_kind", "player"), sell_order.get("actor_kind", "player")),
    )
    total_fee = buyer_fee + seller_fee
    insurance = (total_fee * 3 / 10).quantize(Decimal("0.000001"))
    burned = total_fee - insurance
    if shorts_reserve_enabled:
        await credit_short_reserve(
            db, coin_id=str(coin_id), amount=insurance, source_type="spot_fee", source_id=str(trade_id),
        )
        await db.execute(
            "UPDATE player_exchange_fee_fund_v1 SET burned_mora=burned_mora+? WHERE singleton=TRUE", (burned,),
        )
    else:
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
        "SELECT halted_until,halt_reason,halt_public_reason,halt_kind,halted_by,halt_reference_price_micromora,"
        "(halted_until IS NOT NULL AND halted_until>NOW()) AS active "
        "FROM player_coin_market_state_v1 WHERE coin_id=?", (coin_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return {"active": False, "halted_until": None, "reason": None, "public_reason": None,
                "kind": None, "reference_price_micromora": None}
    return {"halted_until": row[0], "reason": row[1], "public_reason": row[2],
            "kind": row[3], "reference_price_micromora": row[5],
            "active": bool(row[6])}


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
        "(coin_id,halted_until,halt_reason,halt_public_reason,halt_kind,halted_by,halt_reference_price_micromora,updated_at) "
        "VALUES(?,NOW()+(? * INTERVAL '1 minute'),?,?,'automatic',NULL,?,NOW()) "
        "ON CONFLICT(coin_id) DO UPDATE SET halted_until=GREATEST("
        "COALESCE(player_coin_market_state_v1.halted_until,NOW()),EXCLUDED.halted_until),"
        "halt_reason=CASE WHEN player_coin_market_state_v1.halt_kind='manual' "
        "AND player_coin_market_state_v1.halted_until>NOW() THEN player_coin_market_state_v1.halt_reason "
        "ELSE EXCLUDED.halt_reason END,"
        "halt_public_reason=CASE WHEN player_coin_market_state_v1.halt_kind='manual' "
        "AND player_coin_market_state_v1.halted_until>NOW() THEN player_coin_market_state_v1.halt_public_reason "
        "ELSE EXCLUDED.halt_public_reason END,"
        "halt_kind=CASE WHEN player_coin_market_state_v1.halt_kind='manual' "
        "AND player_coin_market_state_v1.halted_until>NOW() THEN 'manual' ELSE EXCLUDED.halt_kind END,"
        "halted_by=CASE WHEN player_coin_market_state_v1.halt_kind='manual' "
        "AND player_coin_market_state_v1.halted_until>NOW() THEN player_coin_market_state_v1.halted_by ELSE NULL END,"
        "halt_reference_price_micromora=CASE WHEN player_coin_market_state_v1.halt_kind='manual' "
        "AND player_coin_market_state_v1.halted_until>NOW() THEN player_coin_market_state_v1.halt_reference_price_micromora "
        "ELSE EXCLUDED.halt_reference_price_micromora END,"
        "updated_at=NOW()",
        (coin_id, int(minutes), reason, "Резкое изменение цены: торги временно приостановлены.", int(reference_price)),
    )
    await append_event(db, coin_id=coin_id, actor_id=None, event_type="market_halted",
                       action_id=f"market-halt:{uuid4().hex}", payload={
                           "minutes": int(minutes), "reason": reason,
                           "reference_price_micromora": int(reference_price),
                       })


async def set_manual_market_halt(
    db, *, coin_id: str, actor_id: int, minutes: int, public_reason: str, action_id: str,
) -> dict:
    await db.execute(
        "INSERT INTO player_coin_market_state_v1"
        "(coin_id,halted_until,halt_reason,halt_public_reason,halt_kind,halted_by,updated_at) "
        "VALUES(?,NOW()+(? * INTERVAL '1 minute'),'manual_admin_halt',?,'manual',?,NOW()) "
        "ON CONFLICT(coin_id) DO UPDATE SET halted_until=GREATEST("
        "COALESCE(player_coin_market_state_v1.halted_until,NOW()),EXCLUDED.halted_until),"
        "halt_reason=EXCLUDED.halt_reason,halt_public_reason=EXCLUDED.halt_public_reason,"
        "halt_kind='manual',halted_by=EXCLUDED.halted_by,halt_reference_price_micromora=NULL,updated_at=NOW()",
        (coin_id, int(minutes), public_reason, int(actor_id)),
    )
    await append_event(
        db, coin_id=coin_id, actor_id=int(actor_id), event_type="market_halted_manual",
        action_id=action_id, payload={"minutes": int(minutes), "public_reason": public_reason},
    )
    return await market_halt(db, coin_id)


async def public_order_book(db, coin_id: str, levels: int = 20) -> dict:
    level_limit = max(1, min(int(levels), 50))
    async with db.execute(
        "SELECT side,limit_price_micromora,SUM(remaining_units) AS units,COUNT(*) AS orders,"
        "SUM(CASE WHEN actor_kind='treasury' THEN remaining_units ELSE 0 END) AS treasury_units "
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


async def best_quote(db, *, coin_id: str, side: str):
    opposite = "sell" if side == "buy" else "buy"
    direction = "ASC" if side == "buy" else "DESC"
    async with db.execute(
        f"SELECT limit_price_micromora,remaining_units FROM player_coin_orders_v1 "
        f"WHERE coin_id=? AND status='open' AND side=? AND remaining_units>0 "
        f"ORDER BY limit_price_micromora {direction},created_at,id LIMIT 1",
        (coin_id, opposite),
    ) as cursor:
        row = await cursor.fetchone()
    return {"price_micromora": int(row[0]), "units": int(row[1])} if row else None


async def public_recent_trades(db, coin_id: str, limit: int = 50) -> list[dict]:
    async with db.execute(
        "SELECT id,units,price_micromora,gross_mora,created_at FROM player_coin_trades_v1 "
        "WHERE coin_id=? ORDER BY created_at DESC,id DESC LIMIT ?",
        (coin_id, max(1, min(int(limit), 100))),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def short_eligibility_metrics(db, *, coin_id: str) -> dict:
    """Server-owned eligibility inputs; callers must evaluate them under the Spot lock."""
    async with db.execute(
        "SELECT GREATEST(0,EXTRACT(EPOCH FROM (NOW()-launched_at))/86400)::INTEGER AS trading_days "
        "FROM player_coins_v1 WHERE id=?", (str(coin_id),)
    ) as cursor:
        launched = await cursor.fetchone()
    if not launched or launched[0] is None:
        return {"trading_days": 0, "verified_trades": 0, "unique_traders": 0,
                "weekly_volume_mora": Decimal("0"), "depth_5pct_mora": Decimal("0")}
    async with db.execute(
        "SELECT COUNT(*),COALESCE(SUM(gross_mora) FILTER (WHERE created_at>=NOW()-INTERVAL '7 days'),0) "
        "FROM player_coin_trades_v1 WHERE coin_id=?", (str(coin_id),)
    ) as cursor:
        trades = await cursor.fetchone()
    async with db.execute(
        "SELECT COUNT(DISTINCT participant_id) FROM ("
        "SELECT buyer_id AS participant_id FROM player_coin_trades_v1 WHERE coin_id=? UNION ALL "
        "SELECT seller_id AS participant_id FROM player_coin_trades_v1 WHERE coin_id=?) participants",
        (str(coin_id), str(coin_id)),
    ) as cursor:
        participant_row = await cursor.fetchone()
    stats = await public_market_stats(db, str(coin_id))
    return {"trading_days": int(launched[0]), "verified_trades": int(trades[0]),
            "unique_traders": int(participant_row[0]), "weekly_volume_mora": Decimal(trades[1]),
            "depth_5pct_mora": Decimal(stats["depth_5pct"]["total_mora"])}


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
    async with db.execute(
        "SELECT MAX(limit_price_micromora) FILTER (WHERE side='buy'),"
        "MIN(limit_price_micromora) FILTER (WHERE side='sell') "
        "FROM player_coin_orders_v1 WHERE coin_id=? AND status='open' AND remaining_units>0",
        (coin_id,),
    ) as cursor:
        quote_row = await cursor.fetchone()
    best_bid = int(quote_row[0]) if quote_row and quote_row[0] is not None else None
    best_ask = int(quote_row[1]) if quote_row and quote_row[1] is not None else None
    result["best_bid_micromora"] = best_bid
    result["best_ask_micromora"] = best_ask
    result["spread_micromora"] = best_ask - best_bid if best_bid is not None and best_ask is not None else None
    if result["spread_micromora"] is not None and best_bid + best_ask > 0:
        result["spread_percent"] = (
            Decimal(result["spread_micromora"] * 200) / Decimal(best_bid + best_ask)
        ).quantize(Decimal("0.0001"))
    else:
        result["spread_percent"] = None
    five_minute = await vwap_window(db, coin_id=coin_id, minutes=5)
    result["vwap_5m_price_micromora"] = five_minute["vwap_price_micromora"]
    result["volume_5m_mora"] = five_minute["volume_mora"]
    async with db.execute(
        "SELECT COALESCE((SELECT price_micromora FROM player_coin_trades_v1 WHERE coin_id=? "
        "ORDER BY created_at DESC,id DESC LIMIT 1),(SELECT clearing_price_micromora "
        "FROM player_coin_auction_settlements_v1 WHERE coin_id=? AND success=TRUE))",
        (coin_id, coin_id),
    ) as cursor:
        reference_row = await cursor.fetchone()
    reference = (
        five_minute["vwap_price_micromora"]
        or (int(reference_row[0]) if reference_row and reference_row[0] is not None else None)
    )
    result["reference_price_micromora"] = reference
    if reference:
        bid_floor, ask_ceiling = depth_band_bounds(reference)
        async with db.execute(
            "SELECT COALESCE(SUM(CASE WHEN side='buy' AND limit_price_micromora>=? THEN "
            "remaining_units::numeric*limit_price_micromora ELSE 0 END),0),"
            "COALESCE(SUM(CASE WHEN side='sell' AND limit_price_micromora<=? THEN "
            "remaining_units::numeric*limit_price_micromora ELSE 0 END),0) "
            "FROM player_coin_orders_v1 WHERE coin_id=? AND status='open' AND remaining_units>0",
            (bid_floor, ask_ceiling, coin_id),
        ) as cursor:
            depth = await cursor.fetchone()
        divisor = Decimal(TOKEN_SCALE * PRICE_SCALE)
        buy_depth = (Decimal(depth[0]) / divisor).quantize(Decimal("0.000001"))
        sell_depth = (Decimal(depth[1]) / divisor).quantize(Decimal("0.000001"))
        result["depth_5pct"] = {
            "buy_mora": buy_depth, "sell_mora": sell_depth,
            "total_mora": buy_depth + sell_depth,
        }
        async with db.execute("SELECT circulating_units FROM player_coins_v1 WHERE id=?", (coin_id,)) as cursor:
            circulation = await cursor.fetchone()
        result["market_cap_mora"] = (
            Decimal(int(circulation[0])) * Decimal(reference) / divisor
        ).quantize(Decimal("0.000001"))
    else:
        result["depth_5pct"] = {"buy_mora": Decimal("0"), "sell_mora": Decimal("0"),
                                  "total_mora": Decimal("0")}
        result["market_cap_mora"] = None
    halt = await market_halt(db, coin_id)
    result["halt"] = {key: halt[key] for key in ("active", "halted_until", "kind", "public_reason")}
    return result


async def get_emission_by_action(db, *, owner_id: int, action_id: str):
    async with db.execute(
        "SELECT * FROM player_coin_emissions_v1 WHERE owner_id=? AND (action_id=? OR cancel_action_id=?)",
        (int(owner_id), str(action_id), str(action_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def get_emission(db, emission_id: str, *, for_update: bool = False):
    suffix = " FOR UPDATE" if for_update else ""
    async with db.execute("SELECT * FROM player_coin_emissions_v1 WHERE id=?" + suffix, (str(emission_id),)) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def pending_emission(db, coin_id: str):
    async with db.execute(
        "SELECT * FROM player_coin_emissions_v1 WHERE coin_id=? AND status='pending' ORDER BY requested_at DESC LIMIT 1",
        (str(coin_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def owner_has_open_sell(db, *, coin_id: str, owner_id: int) -> bool:
    async with db.execute(
        "SELECT EXISTS(SELECT 1 FROM player_coin_orders_v1 WHERE coin_id=? AND user_id=? "
        "AND side='sell' AND status='open' AND remaining_units>0)",
        (str(coin_id), int(owner_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return bool(row and row[0])


async def emission_cooldown_active(db, coin_id: str) -> bool:
    async with db.execute(
        "SELECT EXISTS(SELECT 1 FROM player_coin_emissions_v1 WHERE coin_id=? "
        "AND requested_at>NOW()-INTERVAL '7 days')", (str(coin_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return bool(row and row[0])


async def create_emission(db, *, coin_id: str, owner_id: int, units: int,
                          circulation_snapshot_units: int, projected_total_supply_units: int,
                          reason: str, action_id: str, wait_hours: int) -> dict:
    emission_id = uuid4().hex
    async with db.execute(
        "INSERT INTO player_coin_emissions_v1"
        "(id,coin_id,owner_id,action_id,requested_units,circulation_snapshot_units,"
        "projected_total_supply_units,reason,executes_at) "
        "VALUES(?,?,?,?,?,?,?,?,NOW()+(? * INTERVAL '1 hour')) RETURNING *",
        (emission_id, str(coin_id), int(owner_id), str(action_id), int(units),
         int(circulation_snapshot_units), int(projected_total_supply_units), reason, int(wait_hours)),
    ) as cursor:
        row = dict(await cursor.fetchone())
    await append_event(
        db, coin_id=str(coin_id), actor_id=int(owner_id), event_type="emission_requested",
        action_id=str(action_id), payload={"emission_id": emission_id, "units": int(units),
            "circulation_snapshot_units": int(circulation_snapshot_units),
            "projected_total_supply_units": int(projected_total_supply_units),
            "reason": reason, "executes_at": row["executes_at"].isoformat()},
    )
    return row


async def cancel_emission(db, *, emission_id: str, owner_id: int, action_id: str) -> dict:
    async with db.execute(
        "UPDATE player_coin_emissions_v1 SET status='cancelled',cancel_action_id=?,cancelled_at=NOW() "
        "WHERE id=? AND owner_id=? AND status='pending' "
        "AND executes_at>NOW()+INTERVAL '60 minutes' RETURNING *",
        (str(action_id), str(emission_id), int(owner_id)),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise ValueError("Emission cannot be cancelled")
    result = dict(row)
    await append_event(
        db, coin_id=str(result["coin_id"]), actor_id=int(owner_id), event_type="emission_cancelled",
        action_id=str(action_id), payload={"emission_id": str(emission_id), "units": int(result["requested_units"])},
    )
    return result


async def due_emission_ids(db, *, limit: int = 20) -> list[str]:
    async with db.execute(
        "SELECT id FROM player_coin_emissions_v1 WHERE status='pending' AND executes_at<=NOW() "
        "ORDER BY executes_at,id LIMIT ?", (max(1, min(int(limit), 100)),),
    ) as cursor:
        return [str(row[0]) for row in await cursor.fetchall()]


async def execute_emission(db, *, emission_id: str) -> dict:
    emission = await get_emission(db, emission_id, for_update=True)
    if not emission or emission["status"] != "pending":
        return emission or {}
    if emission["executes_at"] > datetime.now(emission["executes_at"].tzinfo):
        raise ValueError("Emission is not due")
    units = int(emission["requested_units"])
    async with db.execute(
        "UPDATE player_coin_accounts_v1 SET available_units=available_units+?,updated_at=NOW() "
        "WHERE coin_id=? AND account_kind='treasury' RETURNING 1",
        (units, str(emission["coin_id"])),
    ) as cursor:
        if not await cursor.fetchone():
            raise RuntimeError("Treasury emission account missing")
    await db.execute(
        "UPDATE player_coins_v1 SET total_supply_units=total_supply_units+? WHERE id=?",
        (units, str(emission["coin_id"])),
    )
    async with db.execute(
        "UPDATE player_coin_emissions_v1 SET status='executed',executed_at=NOW() "
        "WHERE id=? AND status='pending' RETURNING *", (str(emission_id),),
    ) as cursor:
        result = dict(await cursor.fetchone())
    await append_event(
        db, coin_id=str(result["coin_id"]), actor_id=int(result["owner_id"]),
        event_type="emission_executed", action_id=f"emission-execute:{emission_id}",
        payload={"emission_id": str(emission_id), "units": units, "destination": "treasury"},
    )
    return result


async def public_emissions(db, coin_id: str, *, limit: int = 20) -> list[dict]:
    async with db.execute(
        "SELECT id,requested_units,circulation_snapshot_units,projected_total_supply_units,"
        "reason,status,requested_at,executes_at,cancelled_at,executed_at,"
        "(status='pending' AND executes_at>NOW()+INTERVAL '1 hour') AS can_cancel "
        "FROM player_coin_emissions_v1 WHERE coin_id=? ORDER BY requested_at DESC,id DESC LIMIT ?",
        (str(coin_id), max(1, min(int(limit), 50))),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def get_liquidity_withdrawal_by_action(db, *, owner_id: int, action_id: str) -> dict | None:
    async with db.execute(
        "SELECT * FROM player_coin_liquidity_withdrawals_v1 "
        "WHERE owner_id=? AND (action_id=? OR cancel_action_id=?)",
        (int(owner_id), str(action_id), str(action_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def get_liquidity_withdrawal(db, withdrawal_id: str, *, for_update: bool = False) -> dict | None:
    suffix = " FOR UPDATE" if for_update else ""
    async with db.execute(
        "SELECT * FROM player_coin_liquidity_withdrawals_v1 WHERE id=?" + suffix,
        (str(withdrawal_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def pending_liquidity_withdrawal(db, coin_id: str) -> dict | None:
    async with db.execute(
        "SELECT * FROM player_coin_liquidity_withdrawals_v1 WHERE coin_id=? AND status='pending' "
        "ORDER BY requested_at DESC LIMIT 1",
        (str(coin_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def liquidity_withdrawal_cooldown_active(db, coin_id: str, *, days: int) -> bool:
    async with db.execute(
        "SELECT EXISTS(SELECT 1 FROM player_coin_liquidity_withdrawals_v1 "
        "WHERE coin_id=? AND status='executed' AND executed_at>NOW()-(? * INTERVAL '1 day'))",
        (str(coin_id), int(days)),
    ) as cursor:
        row = await cursor.fetchone()
    return bool(row[0])


async def create_liquidity_withdrawal(
    db, *, coin_id: str, owner_id: int, amount_mora, treasury_snapshot_mora,
    max_amount_mora, action_id: str, wait_hours: int,
) -> dict:
    withdrawal_id = uuid4().hex
    async with db.execute(
        "INSERT INTO player_coin_liquidity_withdrawals_v1"
        "(id,coin_id,owner_id,action_id,amount_mora,treasury_snapshot_mora,max_amount_mora,executes_at) "
        "VALUES(?,?,?,?,?,?,?,NOW()+(? * INTERVAL '1 hour')) RETURNING *",
        (withdrawal_id, str(coin_id), int(owner_id), str(action_id), amount_mora,
         treasury_snapshot_mora, max_amount_mora, int(wait_hours)),
    ) as cursor:
        return dict(await cursor.fetchone())


async def cancel_liquidity_withdrawal(db, *, withdrawal_id: str, owner_id: int, action_id: str) -> dict:
    async with db.execute(
        "UPDATE player_coin_liquidity_withdrawals_v1 SET status='cancelled',cancel_action_id=?,cancelled_at=NOW() "
        "WHERE id=? AND owner_id=? AND status='pending' RETURNING *",
        (str(action_id), str(withdrawal_id), int(owner_id)),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise ValueError("withdrawal cannot be cancelled")
    return dict(row)


async def due_liquidity_withdrawal_ids(db, *, limit: int = 20) -> list[str]:
    async with db.execute(
        "SELECT id FROM player_coin_liquidity_withdrawals_v1 WHERE status='pending' AND executes_at<=NOW() "
        "ORDER BY executes_at,id LIMIT ?",
        (max(1, min(int(limit), 100)),),
    ) as cursor:
        return [str(row[0]) for row in await cursor.fetchall()]


async def mark_liquidity_withdrawal_executed(
    db, *, withdrawal_id: str, economy_operation_id: str,
) -> dict:
    async with db.execute(
        "UPDATE player_coin_liquidity_withdrawals_v1 SET status='executed',economy_operation_id=?,executed_at=NOW() "
        "WHERE id=? AND status='pending' RETURNING *",
        (str(economy_operation_id), str(withdrawal_id)),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise ValueError("withdrawal is no longer pending")
    return dict(row)


async def public_liquidity_withdrawals(db, coin_id: str, *, limit: int = 20) -> list[dict]:
    async with db.execute(
        "SELECT id,amount_mora,treasury_snapshot_mora,max_amount_mora,status,requested_at,executes_at,cancelled_at,executed_at "
        "FROM player_coin_liquidity_withdrawals_v1 WHERE coin_id=? ORDER BY requested_at DESC,id DESC LIMIT ?",
        (str(coin_id), max(1, min(int(limit), 50))),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def owner_vesting_state(db, coin_id: str, *, for_update: bool = False) -> dict | None:
    suffix = " FOR UPDATE OF c,a" if for_update else ""
    async with db.execute(
        "SELECT c.id AS coin_id,c.owner_id,c.status,c.launched_at,c.genesis_units,"
        "a.available_units AS locked_units,a.reserved_units,"
        "GREATEST(0,EXTRACT(EPOCH FROM (NOW()-c.launched_at))) AS age_seconds,"
        "NOW() AS server_now FROM player_coins_v1 c "
        "JOIN player_coin_accounts_v1 a ON a.coin_id=c.id AND a.account_kind='owner_locked' "
        "WHERE c.id=?" + suffix,
        (str(coin_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def transfer_vested_owner_units(db, *, coin_id: str, owner_id: int, units: int) -> None:
    async with db.execute(
        "UPDATE player_coin_accounts_v1 SET available_units=available_units-?,updated_at=NOW() "
        "WHERE coin_id=? AND account_kind='owner_locked' AND available_units>=? RETURNING 1",
        (int(units), str(coin_id), int(units)),
    ) as cursor:
        if not await cursor.fetchone():
            raise RuntimeError("Owner vesting lock invariant failed.")
    await db.execute(
        "INSERT INTO player_coin_accounts_v1"
        "(coin_id,account_key,account_kind,user_id,available_units,reserved_units) "
        "VALUES(?,?,'player',?,?,0) ON CONFLICT(coin_id,account_key) DO UPDATE SET "
        "available_units=player_coin_accounts_v1.available_units+EXCLUDED.available_units,updated_at=NOW()",
        (str(coin_id), f"player:{int(owner_id)}", int(owner_id), int(units)),
    )
    async with db.execute(
        "UPDATE player_coins_v1 SET circulating_units=circulating_units+? WHERE id=? RETURNING 1",
        (int(units), str(coin_id)),
    ) as cursor:
        if not await cursor.fetchone():
            raise RuntimeError("Owner vesting circulation invariant failed.")


async def public_owner_journal(db, coin_id: str, *, limit: int = 50) -> list[dict]:
    public_types = (
        "coin_created", "auction_settled", "treasury_ladder_created",
        "market_halted", "market_halted_manual", "emission_requested",
        "emission_cancelled", "emission_executed", "owner_vesting_claimed",
        "treasury_order_placed", "treasury_order_cancelled", "treasury_burned",
        "liquidity_added", "liquidity_withdrawal_requested", "liquidity_withdrawal_cancelled",
        "liquidity_withdrawal_executed",
    )
    placeholders = ",".join("?" for _ in public_types)
    async with db.execute(
        "SELECT id,event_type,payload_json,created_at FROM player_coin_events_v1 "
        f"WHERE coin_id=? AND event_type IN ({placeholders}) "
        "ORDER BY created_at DESC,id DESC LIMIT ?",
        (str(coin_id), *public_types, max(1, min(int(limit), 100))),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def public_treasury_state(db, coin_id: str) -> dict:
    async with db.execute(
        "SELECT m.treasury_mora,m.insurance_mora,"
        "COALESCE(SUM(a.available_units) FILTER (WHERE a.account_kind='treasury'),0) AS treasury_units,"
        "COALESCE(SUM(a.reserved_units) FILTER (WHERE a.account_kind='treasury'),0) AS treasury_reserved_units,"
        "COALESCE(SUM(a.available_units) FILTER (WHERE a.account_kind='market_reserve'),0) AS market_reserve_units,"
        "COALESCE(SUM(a.reserved_units) FILTER (WHERE a.account_kind='market_reserve'),0) AS market_reserved_units "
        "FROM player_coin_mora_accounts_v1 m JOIN player_coin_accounts_v1 a ON a.coin_id=m.coin_id "
        "WHERE m.coin_id=? GROUP BY m.treasury_mora,m.insurance_mora",
        (str(coin_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else {}


async def public_treasury_orders(db, coin_id: str, *, limit: int = 50) -> list[dict]:
    async with db.execute(
        "SELECT id,side,limit_price_micromora,original_units,remaining_units,reserved_mora,status,created_at "
        "FROM player_coin_orders_v1 WHERE coin_id=? AND actor_kind='treasury' "
        "ORDER BY (status='open') DESC,created_at DESC,id DESC LIMIT ?",
        (str(coin_id), max(1, min(int(limit), 100))),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]
