"""Append-only internal storage for future Echo Shard compensations."""
from __future__ import annotations

import json
from typing import Any


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS echo_shard_accounts_v1 (
            user_id BIGINT PRIMARY KEY,
            balance BIGINT NOT NULL DEFAULT 0 CHECK(balance >= 0),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS echo_shard_compensations_v1 (
            id TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            source_kind TEXT NOT NULL,
            source_event_id TEXT NOT NULL,
            source_line_id INTEGER NOT NULL CHECK(source_line_id >= 0),
            collectible_kind TEXT NOT NULL,
            collectible_id TEXT NOT NULL,
            observed_level INTEGER NOT NULL CHECK(observed_level >= 1),
            observed_cap INTEGER NOT NULL CHECK(observed_cap >= 1),
            amount BIGINT NOT NULL CHECK(amount > 0),
            policy_version TEXT NOT NULL,
            source_snapshot JSONB NOT NULL,
            source_snapshot_hash TEXT NOT NULL CHECK(source_snapshot_hash ~ '^[0-9a-f]{64}$'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK(observed_level = observed_cap),
            CHECK(source_kind <> 'pet_v1_max_duplicate' OR amount = 1),
            UNIQUE(user_id, source_kind, source_event_id, source_line_id)
        )
    """)
    # The first foundation was deliberately empty in production.  These guarded
    # migrations also make a later local restart fail closed for legacy rows.
    await db.execute("ALTER TABLE echo_shard_compensations_v1 ADD COLUMN IF NOT EXISTS source_snapshot_hash TEXT")
    # v1 originally keyed a receipt globally although terminal source ids are
    # per-player.  Keep event identity scoped exactly like the pet receipt.
    await db.execute("""
        DO $$
        DECLARE old_constraint TEXT;
        BEGIN
            SELECT conname INTO old_constraint
            FROM pg_constraint
            WHERE conrelid = 'echo_shard_compensations_v1'::regclass
              AND contype = 'u'
              AND pg_get_constraintdef(oid) LIKE 'UNIQUE (source_kind, source_event_id, source_line_id)%'
            LIMIT 1;
            IF old_constraint IS NOT NULL THEN
                EXECUTE format('ALTER TABLE echo_shard_compensations_v1 DROP CONSTRAINT %I', old_constraint);
            END IF;
        END $$
    """)
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_echo_shard_source_per_user_v1
        ON echo_shard_compensations_v1(user_id, source_kind, source_event_id, source_line_id)
    """)
    await db.execute("ALTER TABLE echo_shard_compensations_v1 DROP CONSTRAINT IF EXISTS echo_shard_snapshot_hash_v1")
    await db.execute("""
        ALTER TABLE echo_shard_compensations_v1
        ADD CONSTRAINT echo_shard_snapshot_hash_v1
        CHECK(source_snapshot_hash IS NOT NULL AND source_snapshot_hash ~ '^[0-9a-f]{64}$') NOT VALID
    """)
    await db.execute("ALTER TABLE echo_shard_compensations_v1 DROP CONSTRAINT IF EXISTS echo_shard_pet_amount_v1")
    await db.execute("""
        ALTER TABLE echo_shard_compensations_v1
        ADD CONSTRAINT echo_shard_pet_amount_v1
        CHECK(source_kind <> 'pet_v1_max_duplicate' OR amount = 1) NOT VALID
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS echo_shard_ledger_v1 (
            id BIGSERIAL PRIMARY KEY,
            compensation_id TEXT NOT NULL UNIQUE REFERENCES echo_shard_compensations_v1(id) ON DELETE RESTRICT,
            user_id BIGINT NOT NULL,
            delta BIGINT NOT NULL CHECK(delta > 0),
            balance_before BIGINT NOT NULL CHECK(balance_before >= 0),
            balance_after BIGINT NOT NULL CHECK(balance_after = balance_before + delta),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE OR REPLACE FUNCTION reject_echo_shard_ledger_rewrite_v1()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'echo_shard_ledger_v1 is append-only';
        END;
        $$
    """)
    await db.execute("DROP TRIGGER IF EXISTS echo_shard_ledger_append_only_v1 ON echo_shard_ledger_v1")
    await db.execute("""
        CREATE TRIGGER echo_shard_ledger_append_only_v1
        BEFORE UPDATE OR DELETE ON echo_shard_ledger_v1
        FOR EACH ROW EXECUTE FUNCTION reject_echo_shard_ledger_rewrite_v1()
    """)
    await db.execute("""
        CREATE OR REPLACE FUNCTION reject_echo_shard_compensation_rewrite_v1()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'echo_shard_compensations_v1 is append-only';
        END;
        $$
    """)
    await db.execute("DROP TRIGGER IF EXISTS echo_shard_compensations_append_only_v1 ON echo_shard_compensations_v1")
    await db.execute("""
        CREATE TRIGGER echo_shard_compensations_append_only_v1
        BEFORE UPDATE OR DELETE ON echo_shard_compensations_v1
        FOR EACH ROW EXECUTE FUNCTION reject_echo_shard_compensation_rewrite_v1()
    """)


async def lock_user(db, user_id: int) -> None:
    async with db.execute("SELECT pg_advisory_xact_lock(?)", (int(user_id),)) as cursor:
        await cursor.fetchone()


async def find_by_source(db, *, user_id: int, source_kind: str, source_event_id: str, source_line_id: int) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT c.*,l.balance_before,l.balance_after FROM echo_shard_compensations_v1 c "
        "JOIN echo_shard_ledger_v1 l ON l.compensation_id=c.id "
        "WHERE c.user_id=? AND c.source_kind=? AND c.source_event_id=? AND c.source_line_id=?",
        (int(user_id), source_kind, source_event_id, int(source_line_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def get_balance(db, user_id: int) -> int:
    """Read the isolated Echo Shard account without creating or locking it."""
    async with db.execute(
        "SELECT balance FROM echo_shard_accounts_v1 WHERE user_id=?", (int(user_id),)
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def lock_account(db, user_id: int) -> int:
    await db.execute(
        "INSERT INTO echo_shard_accounts_v1(user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING",
        (int(user_id),),
    )
    async with db.execute(
        "SELECT balance FROM echo_shard_accounts_v1 WHERE user_id=? FOR UPDATE", (int(user_id),)
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise RuntimeError("Echo Shard account was not created.")
    return int(row[0])


async def apply_compensation(
    db, *, compensation_id: str, user_id: int, source_kind: str, source_event_id: str,
    source_line_id: int, collectible_kind: str, collectible_id: str, observed_level: int,
    observed_cap: int, amount: int, policy_version: str, source_snapshot: dict[str, Any], source_snapshot_hash: str,
    balance_before: int,
) -> int:
    encoded_snapshot = json.dumps(source_snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    balance_after = int(balance_before) + int(amount)
    await db.execute(
        "INSERT INTO echo_shard_compensations_v1 "
        "(id,user_id,source_kind,source_event_id,source_line_id,collectible_kind,collectible_id,observed_level,observed_cap,amount,policy_version,source_snapshot,source_snapshot_hash) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?::jsonb,?)",
        (compensation_id, int(user_id), source_kind, source_event_id, int(source_line_id), collectible_kind,
         collectible_id, int(observed_level), int(observed_cap), int(amount), policy_version, encoded_snapshot, source_snapshot_hash),
    )
    await db.execute(
        "UPDATE echo_shard_accounts_v1 SET balance=?,updated_at=NOW() WHERE user_id=?",
        (balance_after, int(user_id)),
    )
    await db.execute(
        "INSERT INTO echo_shard_ledger_v1(compensation_id,user_id,delta,balance_before,balance_after) VALUES (?,?,?,?,?)",
        (compensation_id, int(user_id), int(amount), int(balance_before), balance_after),
    )
    return balance_after
