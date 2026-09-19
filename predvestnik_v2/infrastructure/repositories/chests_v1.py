"""Append-only storage for the approved chest-key foundation."""
from __future__ import annotations

import json
from typing import Any


async def ensure_tables(db) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS user_cosmetics ("
        "user_id BIGINT NOT NULL, cosmetic_id TEXT NOT NULL, acquired_at TIMESTAMP DEFAULT NOW(), "
        "PRIMARY KEY(user_id,cosmetic_id))"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chest_key_accounts_v1 (
            user_id BIGINT PRIMARY KEY,
            balance BIGINT NOT NULL DEFAULT 0 CHECK(balance >= 0),
            account_epoch BIGINT NOT NULL DEFAULT 0 CHECK(account_epoch >= 0),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP()
        )
    """)
    await db.execute(
        "ALTER TABLE chest_key_accounts_v1 ADD COLUMN IF NOT EXISTS account_epoch BIGINT NOT NULL DEFAULT 0"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chest_account_retirements_v1 (
            user_id BIGINT NOT NULL,
            old_epoch BIGINT NOT NULL CHECK(old_epoch >= 0),
            new_epoch BIGINT NOT NULL CHECK(new_epoch = old_epoch + 1),
            balance_before BIGINT NOT NULL CHECK(balance_before >= 0),
            balance_after BIGINT NOT NULL DEFAULT 0 CHECK(balance_after = 0),
            reason TEXT NOT NULL CHECK(reason = 'account_finalization'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(),
            PRIMARY KEY(user_id,new_epoch)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chest_key_grants_v1 (
            id TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            source_kind TEXT NOT NULL CHECK(source_kind IN (
                'quest_daily_set_complete','quest_weekly_set_complete'
            )),
            source_event_id TEXT NOT NULL,
            amount SMALLINT NOT NULL CHECK(amount = 1),
            policy_version TEXT NOT NULL,
            source_snapshot JSONB NOT NULL,
            source_snapshot_hash TEXT NOT NULL CHECK(source_snapshot_hash ~ '^[0-9a-f]{64}$'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(),
            UNIQUE(user_id, source_kind, source_event_id)
        )
    """)
    await db.execute("ALTER TABLE chest_key_grants_v1 ADD COLUMN IF NOT EXISTS account_epoch BIGINT NOT NULL DEFAULT 0")
    await db.execute("""
        DO $$ DECLARE item RECORD; BEGIN
          FOR item IN SELECT conname FROM pg_constraint
            WHERE conrelid='chest_key_grants_v1'::regclass AND contype='c'
              AND pg_get_constraintdef(oid) LIKE '%source_kind%'
          LOOP EXECUTE format('ALTER TABLE chest_key_grants_v1 DROP CONSTRAINT %I',item.conname); END LOOP;
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chest_key_grants_v1_source_kind_release') THEN
            ALTER TABLE chest_key_grants_v1 ADD CONSTRAINT chest_key_grants_v1_source_kind_release
            CHECK(source_kind IN ('quest_daily_set_complete','quest_weekly_set_complete','zarniki_purchase',
                                  'pet_trek_complete','pet_expedition_complete'));
          END IF;
        END $$
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chest_key_ledger_v1 (
            id BIGSERIAL PRIMARY KEY,
            grant_id TEXT NOT NULL UNIQUE REFERENCES chest_key_grants_v1(id) ON DELETE RESTRICT,
            user_id BIGINT NOT NULL,
            delta SMALLINT NOT NULL CHECK(delta = 1),
            balance_before BIGINT NOT NULL CHECK(balance_before >= 0),
            balance_after BIGINT NOT NULL CHECK(balance_after = balance_before + delta),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP()
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chest_opens_v1 (
            id TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            action_id TEXT NOT NULL,
            request_hash TEXT NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
            catalog_version TEXT NOT NULL,
            catalog_digest TEXT NOT NULL CHECK(catalog_digest ~ '^[0-9a-f]{64}$'),
            roll INTEGER NOT NULL CHECK(roll BETWEEN 0 AND 9999),
            stars SMALLINT NOT NULL CHECK(stars BETWEEN 1 AND 10),
            reward_kind TEXT NOT NULL CHECK(reward_kind = 'mora'),
            reward_amount BIGINT NOT NULL CHECK(reward_amount > 0),
            economy_operation_id TEXT NULL,
            account_epoch BIGINT NOT NULL DEFAULT 0 CHECK(account_epoch >= 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(),
            UNIQUE(user_id, action_id)
        )
    """)
    await db.execute("ALTER TABLE chest_opens_v1 ADD COLUMN IF NOT EXISTS reward_ref TEXT NULL")
    await db.execute("ALTER TABLE chest_opens_v1 ADD COLUMN IF NOT EXISTS reward_rarity TEXT NULL")
    await db.execute("""
        DO $$ DECLARE item RECORD; BEGIN
          FOR item IN SELECT conname FROM pg_constraint
            WHERE conrelid='chest_opens_v1'::regclass AND contype='c'
              AND pg_get_constraintdef(oid) LIKE '%reward_kind%'
          LOOP EXECUTE format('ALTER TABLE chest_opens_v1 DROP CONSTRAINT %I',item.conname); END LOOP;
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chest_opens_v1_reward_kind_release') THEN
            ALTER TABLE chest_opens_v1 ADD CONSTRAINT chest_opens_v1_reward_kind_release
            CHECK(reward_kind IN ('mora','diamonds','zarniki','food','pet_card','joker','vip_days','vip_cosmetic'));
          END IF;
        END $$
    """)
    await db.execute("ALTER TABLE chest_opens_v1 ALTER COLUMN economy_operation_id DROP NOT NULL")
    await db.execute(
        "ALTER TABLE chest_opens_v1 ADD COLUMN IF NOT EXISTS account_epoch BIGINT NOT NULL DEFAULT 0"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chest_key_spends_v1 (
            open_id TEXT PRIMARY KEY REFERENCES chest_opens_v1(id) ON DELETE RESTRICT,
            user_id BIGINT NOT NULL,
            amount SMALLINT NOT NULL CHECK(amount = 1),
            balance_before BIGINT NOT NULL CHECK(balance_before > 0),
            balance_after BIGINT NOT NULL CHECK(balance_after = balance_before - amount),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP()
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chest_reveals_v1 (
            open_id TEXT PRIMARY KEY REFERENCES chest_opens_v1(id) ON DELETE RESTRICT,
            user_id BIGINT NOT NULL,
            economy_operation_id TEXT NULL,
            revealed_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP()
        )
    """)
    await db.execute(
        "ALTER TABLE chest_reveals_v1 ADD COLUMN IF NOT EXISTS economy_operation_id TEXT NULL"
    )
    # One earlier local canary revision credited at prepare time and stored the
    # canonical operation on the open. Migration is one transaction: an
    # unbackfillable row rolls the trigger DROP back too, never leaving mutable
    # history behind while startup continues after logging the failure.
    async with db.connection.transaction():
        await db.execute("DROP TRIGGER IF EXISTS chest_reveals_v1_append_only ON chest_reveals_v1")
        await db.execute(
            "UPDATE chest_reveals_v1 r SET economy_operation_id=o.economy_operation_id "
            "FROM chest_opens_v1 o WHERE o.id=r.open_id AND r.economy_operation_id IS NULL "
            "AND o.economy_operation_id IS NOT NULL"
        )
        async with db.execute(
            "SELECT COUNT(*) FROM chest_reveals_v1 WHERE economy_operation_id IS NULL"
        ) as cursor:
            if int((await cursor.fetchone())[0]):
                raise RuntimeError("Chest reveal migration found a delivery without an economic operation.")
        await db.execute("ALTER TABLE chest_reveals_v1 ALTER COLUMN economy_operation_id SET NOT NULL")
        await db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_chest_reveals_v1_economy_operation_full "
            "ON chest_reveals_v1(economy_operation_id)"
        )
        await db.execute("""
            DO $$ BEGIN
                IF to_regclass('economic_operations') IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname='fk_chest_reveal_economy_operation_v1'
                ) THEN
                    ALTER TABLE chest_reveals_v1 ADD CONSTRAINT fk_chest_reveal_economy_operation_v1
                    FOREIGN KEY (economy_operation_id) REFERENCES economic_operations(id) ON DELETE RESTRICT;
                END IF;
            END $$
        """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chest_key_purchases_v1 (
            id TEXT PRIMARY KEY, user_id BIGINT NOT NULL, action_id TEXT NOT NULL,
            request_hash TEXT NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
            catalog_version TEXT NOT NULL, catalog_digest TEXT NOT NULL CHECK(catalog_digest ~ '^[0-9a-f]{64}$'),
            price_zarniki SMALLINT NOT NULL CHECK(price_zarniki > 0),
            economy_operation_id TEXT NOT NULL UNIQUE REFERENCES economic_operations(id) ON DELETE RESTRICT,
            purchased_on DATE NOT NULL DEFAULT ((CLOCK_TIMESTAMP() AT TIME ZONE 'UTC')::date),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(), UNIQUE(user_id,action_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chest_key_allocations_v1 (
            open_id TEXT PRIMARY KEY REFERENCES chest_opens_v1(id) ON DELETE RESTRICT,
            grant_id TEXT NOT NULL UNIQUE REFERENCES chest_key_grants_v1(id) ON DELETE RESTRICT,
            user_id BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP()
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chest_key_refunds_v1 (
            id TEXT PRIMARY KEY, user_id BIGINT NOT NULL,
            purchase_id TEXT NOT NULL UNIQUE REFERENCES chest_key_purchases_v1(id) ON DELETE RESTRICT,
            action_id TEXT NOT NULL, request_hash TEXT NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
            amount_zarniki SMALLINT NOT NULL CHECK(amount_zarniki > 0),
            economy_operation_id TEXT NOT NULL UNIQUE REFERENCES economic_operations(id) ON DELETE RESTRICT,
            reason TEXT NOT NULL CHECK(reason IN ('delivery_failure','owner_approved_support')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(), UNIQUE(user_id,action_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chest_key_revocations_v1 (
            refund_id TEXT PRIMARY KEY REFERENCES chest_key_refunds_v1(id) ON DELETE RESTRICT,
            grant_id TEXT NOT NULL UNIQUE REFERENCES chest_key_grants_v1(id) ON DELETE RESTRICT,
            user_id BIGINT NOT NULL, balance_before BIGINT NOT NULL CHECK(balance_before > 0),
            balance_after BIGINT NOT NULL CHECK(balance_after=balance_before-1),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP()
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chest_food_balances_v1 (
            user_id BIGINT NOT NULL, food_id TEXT NOT NULL, quantity BIGINT NOT NULL CHECK(quantity >= 0),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(), PRIMARY KEY(user_id,food_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chest_pet_card_balances_v1 (
            user_id BIGINT NOT NULL, species_id TEXT NOT NULL, quantity BIGINT NOT NULL CHECK(quantity >= 0),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(), PRIMARY KEY(user_id,species_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chest_joker_balances_v1 (
            user_id BIGINT NOT NULL, rarity TEXT NOT NULL, quantity BIGINT NOT NULL CHECK(quantity >= 0),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(), PRIMARY KEY(user_id,rarity)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chest_pet_unlocks_v1 (
            user_id BIGINT NOT NULL, species_id TEXT NOT NULL, pet_id BIGINT NOT NULL UNIQUE,
            open_id TEXT NOT NULL UNIQUE REFERENCES chest_opens_v1(id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(), PRIMARY KEY(user_id,species_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chest_deliveries_v1 (
            open_id TEXT PRIMARY KEY REFERENCES chest_opens_v1(id) ON DELETE RESTRICT,
            user_id BIGINT NOT NULL, reward_kind TEXT NOT NULL, reward_ref TEXT NULL,
            reward_amount BIGINT NOT NULL CHECK(reward_amount > 0), operation_id TEXT NOT NULL UNIQUE
                REFERENCES economic_operations(id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP()
        )
    """)
    await db.execute("""
        CREATE OR REPLACE FUNCTION reject_chest_key_history_rewrite_v1()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'chest key history is append-only';
        END;
        $$
    """)
    for table in ("chest_account_retirements_v1", "chest_key_grants_v1", "chest_key_ledger_v1", "chest_opens_v1",
                  "chest_key_spends_v1", "chest_reveals_v1", "chest_key_purchases_v1",
                  "chest_key_allocations_v1", "chest_key_refunds_v1", "chest_key_revocations_v1",
                  "chest_pet_unlocks_v1", "chest_deliveries_v1"):
        trigger = f"{table}_append_only"
        await db.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
        await db.execute(f"""
            CREATE TRIGGER {trigger}
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_chest_key_history_rewrite_v1()
        """)
    await db.commit()


async def lock_user(db, user_id: int) -> None:
    async with db.execute("SELECT pg_advisory_xact_lock(?)", (int(user_id),)) as cursor:
        await cursor.fetchone()


async def assert_delivery_ready(db) -> None:
    """Fail closed if the reveal delivery migration did not fully seal."""
    async with db.execute("""
        SELECT a.attnotnull,
               EXISTS(
                   SELECT 1 FROM pg_constraint c
                   WHERE c.conname='fk_chest_reveal_economy_operation_v1'
                     AND c.contype='f'
                     AND c.conrelid='chest_reveals_v1'::regclass
                     AND c.confrelid='economic_operations'::regclass
                     AND c.conkey=ARRAY[a.attnum]::smallint[]
               ),
               EXISTS(
                   SELECT 1 FROM pg_index i
                   JOIN pg_class ix ON ix.oid=i.indexrelid
                   WHERE ix.relname='uq_chest_reveals_v1_economy_operation_full'
                     AND i.indrelid='chest_reveals_v1'::regclass
                     AND i.indisunique AND i.indpred IS NULL
                     AND i.indnkeyatts=1 AND i.indkey::text=a.attnum::text
               ),
               EXISTS(
                   SELECT 1 FROM pg_trigger t
                   JOIN pg_proc p ON p.oid=t.tgfoid
                   WHERE t.tgrelid='chest_reveals_v1'::regclass
                     AND t.tgname='chest_reveals_v1_append_only'
                     AND NOT t.tgisinternal AND t.tgenabled <> 'D'
                     AND p.proname='reject_chest_key_history_rewrite_v1'
               ),
               (SELECT COUNT(*) FROM chest_reveals_v1 WHERE economy_operation_id IS NULL)
        FROM pg_attribute a
        WHERE a.attrelid='chest_reveals_v1'::regclass
          AND a.attname='economy_operation_id' AND NOT a.attisdropped
    """) as cursor:
        row = await cursor.fetchone()
    if (not row or not bool(row[0]) or not bool(row[1]) or not bool(row[2])
            or not bool(row[3]) or int(row[4])):
        raise RuntimeError("Chest delivery schema is not ready; canary is fail-closed.")


async def quest_reward_receipt(db, *, user_id: int, reward_id: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT r.*,o.reason_code,o.source_type,o.reference_type,o.reference_id,"
        "o.metadata_json,l.delta AS ledger_amount FROM quest_v1_reward_receipts r "
        "JOIN economic_operations o ON o.user_id=r.user_id "
        "AND o.idempotency_key='quest-v1:' || r.reward_id "
        "JOIN economic_ledger l ON l.operation_id=o.id AND l.user_id=r.user_id AND l.currency='mora' "
        "WHERE r.user_id=? AND r.reward_id=?",
        (int(user_id), str(reward_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def find_grant(
    db, *, user_id: int, source_kind: str, source_event_id: str,
) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT g.*,l.balance_before,l.balance_after FROM chest_key_grants_v1 g "
        "JOIN chest_key_ledger_v1 l ON l.grant_id=g.id "
        "WHERE g.user_id=? AND g.source_kind=? AND g.source_event_id=?",
        (int(user_id), str(source_kind), str(source_event_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def get_balance(db, user_id: int) -> int:
    async with db.execute(
        "SELECT balance FROM chest_key_accounts_v1 WHERE user_id=?", (int(user_id),)
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def lock_account(db, user_id: int) -> dict[str, int]:
    await db.execute(
        "INSERT INTO chest_key_accounts_v1(user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING",
        (int(user_id),),
    )
    async with db.execute(
        "SELECT balance,account_epoch FROM chest_key_accounts_v1 WHERE user_id=? FOR UPDATE", (int(user_id),)
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise RuntimeError("Chest-key account was not created.")
    return {"balance": int(row[0]), "account_epoch": int(row[1])}


async def retire_account(db, user_id: int) -> None:
    """Invalidate all pre-finalization entitlements without rewriting history."""
    await lock_user(db, int(user_id))
    account = await lock_account(db, int(user_id))
    old_epoch = int(account["account_epoch"])
    await db.execute(
        "INSERT INTO chest_account_retirements_v1"
        "(user_id,old_epoch,new_epoch,balance_before,balance_after,reason) "
        "VALUES (?,?,?,?,0,'account_finalization')",
        (int(user_id), old_epoch, old_epoch + 1, int(account["balance"])),
    )
    await db.execute(
        "UPDATE chest_key_accounts_v1 SET balance=0,account_epoch=account_epoch+1,"
        "updated_at=CLOCK_TIMESTAMP() WHERE user_id=?",
        (int(user_id),),
    )
    # Mutable inventories are personal game state, not audit evidence. Immutable
    # purchase/open/delivery receipts above remain available for support.
    await db.execute("DELETE FROM chest_food_balances_v1 WHERE user_id=?", (int(user_id),))
    await db.execute("DELETE FROM chest_pet_card_balances_v1 WHERE user_id=?", (int(user_id),))
    await db.execute("DELETE FROM chest_joker_balances_v1 WHERE user_id=?", (int(user_id),))


async def apply_grant(
    db, *, grant_id: str, user_id: int, source_kind: str, source_event_id: str,
    amount: int, policy_version: str, source_snapshot: dict[str, Any],
    source_snapshot_hash: str, balance_before: int, account_epoch: int = 0,
) -> int:
    encoded = json.dumps(source_snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    balance_after = int(balance_before) + int(amount)
    await db.execute(
        "INSERT INTO chest_key_grants_v1 "
        "(id,user_id,source_kind,source_event_id,amount,policy_version,source_snapshot,source_snapshot_hash,account_epoch) "
        "VALUES (?,?,?,?,?,?,?::jsonb,?,?)",
        (grant_id, int(user_id), source_kind, source_event_id, int(amount), policy_version,
         encoded, source_snapshot_hash, int(account_epoch)),
    )
    await db.execute(
        "UPDATE chest_key_accounts_v1 SET balance=?,updated_at=CLOCK_TIMESTAMP() WHERE user_id=?",
        (balance_after, int(user_id)),
    )
    await db.execute(
        "INSERT INTO chest_key_ledger_v1(grant_id,user_id,delta,balance_before,balance_after) "
        "VALUES (?,?,?,?,?)",
        (grant_id, int(user_id), int(amount), int(balance_before), balance_after),
    )
    return balance_after


async def find_open_by_action(db, *, user_id: int, action_id: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT o.*,s.balance_before AS key_balance_before,s.balance_after AS key_balance_after,"
        "(r.open_id IS NOT NULL) AS revealed,r.economy_operation_id AS reveal_operation_id FROM chest_opens_v1 o "
        "JOIN chest_key_spends_v1 s ON s.open_id=o.id "
        "LEFT JOIN chest_reveals_v1 r ON r.open_id=o.id "
        "JOIN chest_key_accounts_v1 a ON a.user_id=o.user_id AND a.account_epoch=o.account_epoch "
        "WHERE o.user_id=? AND o.action_id=?",
        (int(user_id), str(action_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def get_open(db, *, user_id: int, open_id: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT o.*,s.balance_before AS key_balance_before,s.balance_after AS key_balance_after,"
        "(r.open_id IS NOT NULL) AS revealed,r.economy_operation_id AS reveal_operation_id FROM chest_opens_v1 o "
        "JOIN chest_key_spends_v1 s ON s.open_id=o.id "
        "LEFT JOIN chest_reveals_v1 r ON r.open_id=o.id "
        "JOIN chest_key_accounts_v1 a ON a.user_id=o.user_id AND a.account_epoch=o.account_epoch "
        "WHERE o.user_id=? AND o.id=?",
        (int(user_id), str(open_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def latest_unrevealed_open(db, *, user_id: int) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT o.*,s.balance_before AS key_balance_before,s.balance_after AS key_balance_after,"
        "FALSE AS revealed,NULL::TEXT AS reveal_operation_id FROM chest_opens_v1 o "
        "JOIN chest_key_spends_v1 s ON s.open_id=o.id "
        "LEFT JOIN chest_reveals_v1 r ON r.open_id=o.id "
        "JOIN chest_key_accounts_v1 a ON a.user_id=o.user_id AND a.account_epoch=o.account_epoch "
        "WHERE o.user_id=? AND r.open_id IS NULL ORDER BY o.created_at DESC LIMIT 1",
        (int(user_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def latest_revealed_open(db, *, user_id: int) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT o.*,s.balance_before AS key_balance_before,s.balance_after AS key_balance_after,"
        "TRUE AS revealed,r.economy_operation_id AS reveal_operation_id FROM chest_opens_v1 o "
        "JOIN chest_key_spends_v1 s ON s.open_id=o.id "
        "JOIN chest_reveals_v1 r ON r.open_id=o.id "
        "JOIN chest_key_accounts_v1 a ON a.user_id=o.user_id AND a.account_epoch=o.account_epoch "
        "WHERE o.user_id=? ORDER BY r.revealed_at DESC LIMIT 1",
        (int(user_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def create_open(
    db, *, open_id: str, user_id: int, action_id: str, request_hash: str,
    catalog_version: str, catalog_digest: str, roll: int, stars: int,
    reward_kind: str, reward_amount: int, key_balance_before: int, account_epoch: int,
    reward_ref: str | None = None, reward_rarity: str | None = None, grant_id: str | None = None,
) -> None:
    key_balance_after = int(key_balance_before) - 1
    if key_balance_after < 0:
        raise RuntimeError("Chest key balance cannot become negative.")
    await db.execute(
        "INSERT INTO chest_opens_v1 "
        "(id,user_id,action_id,request_hash,catalog_version,catalog_digest,roll,stars,reward_kind,reward_amount,reward_ref,reward_rarity,economy_operation_id,account_epoch) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (open_id, int(user_id), str(action_id), request_hash, catalog_version, catalog_digest,
         int(roll), int(stars), reward_kind, int(reward_amount), reward_ref, reward_rarity, None, int(account_epoch)),
    )
    async with db.execute(
        "UPDATE chest_key_accounts_v1 SET balance=?,updated_at=CLOCK_TIMESTAMP() "
        "WHERE user_id=? AND balance=? RETURNING 1",
        (key_balance_after, int(user_id), int(key_balance_before)),
    ) as cursor:
        if not await cursor.fetchone():
            raise RuntimeError("Chest key spend lost its guarded account update.")
    await db.execute(
        "INSERT INTO chest_key_spends_v1(open_id,user_id,amount,balance_before,balance_after) VALUES (?,?,1,?,?)",
        (open_id, int(user_id), int(key_balance_before), key_balance_after),
    )
    if grant_id is not None:
        await db.execute(
            "INSERT INTO chest_key_allocations_v1(open_id,grant_id,user_id) VALUES (?,?,?)",
            (str(open_id), str(grant_id), int(user_id)),
        )


async def reveal_open(db, *, user_id: int, open_id: str, economy_operation_id: str) -> bool:
    async with db.execute(
        "INSERT INTO chest_reveals_v1(open_id,user_id,economy_operation_id) "
        "SELECT o.id,o.user_id,e.id FROM chest_opens_v1 o "
        "JOIN economic_operations e ON e.id=? AND e.user_id=o.user_id "
        "AND e.reference_type='chest_open' AND e.reference_id=o.id "
        "WHERE o.id=? AND o.user_id=? "
        "ON CONFLICT(open_id) DO NOTHING RETURNING 1",
        (str(economy_operation_id), str(open_id), int(user_id)),
    ) as cursor:
        return bool(await cursor.fetchone())


async def next_unspent_grant(db, *, user_id: int, account_epoch: int) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT g.* FROM chest_key_grants_v1 g "
        "LEFT JOIN chest_key_allocations_v1 a ON a.grant_id=g.id "
        "LEFT JOIN chest_key_revocations_v1 v ON v.grant_id=g.id "
        "WHERE g.user_id=? AND g.account_epoch=? AND a.grant_id IS NULL AND v.grant_id IS NULL "
        "ORDER BY g.created_at,g.id LIMIT 1 FOR UPDATE OF g",
        (int(user_id), int(account_epoch)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def find_purchase(db, *, user_id: int, action_id: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT p.*,g.id AS grant_id,l.balance_before,l.balance_after "
        "FROM chest_key_purchases_v1 p JOIN chest_key_grants_v1 g "
        "ON g.user_id=p.user_id AND g.source_kind='zarniki_purchase' AND g.source_event_id=p.id "
        "JOIN chest_key_ledger_v1 l ON l.grant_id=g.id WHERE p.user_id=? AND p.action_id=?",
        (int(user_id), str(action_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def paid_purchases_today(db, *, user_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM chest_key_purchases_v1 WHERE user_id=? "
        "AND purchased_on=(CLOCK_TIMESTAMP() AT TIME ZONE 'UTC')::date",
        (int(user_id),),
    ) as cursor:
        return int((await cursor.fetchone())[0])


async def create_purchase(
    db, *, purchase_id: str, user_id: int, action_id: str, request_hash: str,
    catalog_version: str, catalog_digest: str, price_zarniki: int, economy_operation_id: str,
) -> None:
    await db.execute(
        "INSERT INTO chest_key_purchases_v1"
        "(id,user_id,action_id,request_hash,catalog_version,catalog_digest,price_zarniki,economy_operation_id) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (str(purchase_id), int(user_id), str(action_id), request_hash, catalog_version,
         catalog_digest, int(price_zarniki), str(economy_operation_id)),
    )


async def vip_cosmetic_candidates(db, *, user_id: int, allowed_ids: tuple[str, ...]) -> list[str]:
    if not allowed_ids:
        return []
    placeholders = ",".join("?" for _ in allowed_ids)
    async with db.execute(
        f"SELECT candidate.id FROM (VALUES {','.join('( ? )' for _ in allowed_ids)}) AS candidate(id) "
        "WHERE NOT EXISTS (SELECT 1 FROM user_cosmetics u WHERE u.user_id=? AND u.cosmetic_id=candidate.id) "
        "ORDER BY candidate.id",
        (*allowed_ids, int(user_id)),
    ) as cursor:
        return [str(row[0]) for row in await cursor.fetchall()]


async def create_item_operation(
    db, *, operation_id: str, user_id: int, open_id: str, metadata: dict[str, Any],
) -> None:
    encoded = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    request_hash = __import__("hashlib").sha256(encoded.encode("utf-8")).hexdigest()
    await db.execute(
        "INSERT INTO economic_operations"
        "(id,user_id,idempotency_key,request_fingerprint,reason_code,source_type,reference_type,reference_id,metadata_json) "
        "VALUES (?,?,?,?, 'chest_v1_reward','chest_v1','chest_open',?,?::jsonb)",
        (str(operation_id), int(user_id), f"chest-v1:{open_id}:reward", request_hash, str(open_id), encoded),
    )


async def _pet_unlock_receipt_exists(db, *, user_id: int, species_id: str) -> bool:
    async with db.execute(
        "SELECT 1 FROM chest_pet_unlocks_v1 WHERE user_id=? AND species_id=?",
        (int(user_id), str(species_id)),
    ) as cursor:
        return bool(await cursor.fetchone())


async def deliver_inventory_reward(
    db, *, user_id: int, open_id: str, reward_kind: str, reward_ref: str | None,
    reward_amount: int, operation_id: str, species: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply one typed non-currency reward. Caller owns the transaction."""
    unlocked_pet_id = None
    if reward_kind == "food":
        await db.execute(
            "INSERT INTO chest_food_balances_v1(user_id,food_id,quantity) VALUES (?,?,?) "
            "ON CONFLICT(user_id,food_id) DO UPDATE SET quantity=chest_food_balances_v1.quantity+EXCLUDED.quantity,updated_at=CLOCK_TIMESTAMP()",
            (int(user_id), str(reward_ref), int(reward_amount)),
        )
    elif reward_kind == "pet_card":
        async with db.execute(
            "SELECT unlock.pet_id FROM chest_pet_unlocks_v1 unlock WHERE unlock.user_id=? AND unlock.species_id=? "
            "UNION ALL SELECT pet.id FROM pets pet WHERE pet.owner_id=? AND pet.species_id=? LIMIT 1",
            (int(user_id), str(reward_ref), int(user_id), str(reward_ref)),
        ) as cursor:
            owned = await cursor.fetchone()
        stored = int(reward_amount)
        if not owned:
            if not species:
                raise RuntimeError("Pet-card delivery has no canonical species.")
            async with db.execute(
                "INSERT INTO pets(owner_id,species_id,rarity,name,placement,fatigue,is_summoned,pet_level,duplicates_collected,copy_index) "
                "VALUES (?,?,?,?,'storage',0,FALSE,1,1,1) RETURNING id",
                (int(user_id), str(reward_ref), str(species["rarity"]), str(species["name"])),
            ) as cursor:
                unlocked_pet_id = int((await cursor.fetchone())[0])
            await db.execute(
                "INSERT INTO chest_pet_unlocks_v1(user_id,species_id,pet_id,open_id) VALUES (?,?,?,?)",
                (int(user_id), str(reward_ref), unlocked_pet_id, str(open_id)),
            )
            stored -= 1
        elif not await _pet_unlock_receipt_exists(db, user_id=int(user_id), species_id=str(reward_ref)):
            # Reconcile a pet created by an older writer. No card is consumed:
            # ownership already exists and this chest delivered the full pack.
            await db.execute(
                "INSERT INTO chest_pet_unlocks_v1(user_id,species_id,pet_id,open_id) VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
                (int(user_id), str(reward_ref), int(owned[0]), str(open_id)),
            )
        if stored:
            await db.execute(
                "INSERT INTO chest_pet_card_balances_v1(user_id,species_id,quantity) VALUES (?,?,?) "
                "ON CONFLICT(user_id,species_id) DO UPDATE SET quantity=chest_pet_card_balances_v1.quantity+EXCLUDED.quantity,updated_at=CLOCK_TIMESTAMP()",
                (int(user_id), str(reward_ref), stored),
            )
    elif reward_kind == "joker":
        await db.execute(
            "INSERT INTO chest_joker_balances_v1(user_id,rarity,quantity) VALUES (?,?,?) "
            "ON CONFLICT(user_id,rarity) DO UPDATE SET quantity=chest_joker_balances_v1.quantity+EXCLUDED.quantity,updated_at=CLOCK_TIMESTAMP()",
            (int(user_id), str(reward_ref), int(reward_amount)),
        )
    elif reward_kind == "vip_cosmetic":
        await db.execute(
            "INSERT INTO user_cosmetics(user_id,cosmetic_id) VALUES (?,?) ON CONFLICT DO NOTHING",
            (int(user_id), str(reward_ref)),
        )
    else:
        raise RuntimeError("Unsupported inventory reward kind.")
    await db.execute(
        "INSERT INTO chest_deliveries_v1(open_id,user_id,reward_kind,reward_ref,reward_amount,operation_id) "
        "VALUES (?,?,?,?,?,?)",
        (str(open_id), int(user_id), str(reward_kind), reward_ref, int(reward_amount), str(operation_id)),
    )
    return {"unlocked_pet_id": unlocked_pet_id}


async def record_currency_or_vip_delivery(
    db, *, user_id: int, open_id: str, reward_kind: str, reward_ref: str | None,
    reward_amount: int, operation_id: str,
) -> None:
    await db.execute(
        "INSERT INTO chest_deliveries_v1(open_id,user_id,reward_kind,reward_ref,reward_amount,operation_id) "
        "VALUES (?,?,?,?,?,?)",
        (str(open_id), int(user_id), str(reward_kind), reward_ref, int(reward_amount), str(operation_id)),
    )


async def inventory_summary(db, *, user_id: int) -> dict[str, Any]:
    async with db.execute(
        "SELECT food_id,quantity FROM chest_food_balances_v1 WHERE user_id=? ORDER BY food_id",
        (int(user_id),),
    ) as cursor:
        foods = {str(row[0]): int(row[1]) for row in await cursor.fetchall()}
    async with db.execute(
        "SELECT species_id,quantity FROM chest_pet_card_balances_v1 WHERE user_id=? ORDER BY species_id",
        (int(user_id),),
    ) as cursor:
        cards = {str(row[0]): int(row[1]) for row in await cursor.fetchall()}
    async with db.execute(
        "SELECT rarity,quantity FROM chest_joker_balances_v1 WHERE user_id=? ORDER BY rarity",
        (int(user_id),),
    ) as cursor:
        jokers = {str(row[0]): int(row[1]) for row in await cursor.fetchall()}
    async with db.execute(
        "SELECT species_id,pet_id FROM chest_pet_unlocks_v1 WHERE user_id=? ORDER BY species_id",
        (int(user_id),),
    ) as cursor:
        pets = {str(row[0]): int(row[1]) for row in await cursor.fetchall()}
    return {"foods": foods, "pet_cards": cards, "jokers": jokers, "unlocked_pets": pets}


async def find_refund(db, *, user_id: int, action_id: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT r.*,v.grant_id,v.balance_before,v.balance_after FROM chest_key_refunds_v1 r "
        "JOIN chest_key_revocations_v1 v ON v.refund_id=r.id WHERE r.user_id=? AND r.action_id=?",
        (int(user_id), str(action_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def refundable_purchase(db, *, user_id: int, purchase_id: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT p.*,g.id AS grant_id,g.account_epoch AS grant_account_epoch FROM chest_key_purchases_v1 p "
        "JOIN chest_key_grants_v1 g ON g.user_id=p.user_id AND g.source_kind='zarniki_purchase' AND g.source_event_id=p.id "
        "LEFT JOIN chest_key_allocations_v1 a ON a.grant_id=g.id "
        "LEFT JOIN chest_key_revocations_v1 v ON v.grant_id=g.id "
        "WHERE p.user_id=? AND p.id=? AND a.grant_id IS NULL AND v.grant_id IS NULL FOR UPDATE OF p,g",
        (int(user_id), str(purchase_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def apply_refund(
    db, *, refund_id: str, user_id: int, purchase_id: str, action_id: str,
    request_hash: str, amount_zarniki: int, economy_operation_id: str,
    reason: str, grant_id: str, balance_before: int,
) -> int:
    after = int(balance_before) - 1
    if after < 0:
        raise RuntimeError("Refund cannot revoke a missing key.")
    await db.execute(
        "INSERT INTO chest_key_refunds_v1"
        "(id,user_id,purchase_id,action_id,request_hash,amount_zarniki,economy_operation_id,reason) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (str(refund_id), int(user_id), str(purchase_id), str(action_id), request_hash,
         int(amount_zarniki), str(economy_operation_id), str(reason)),
    )
    await db.execute(
        "INSERT INTO chest_key_revocations_v1(refund_id,grant_id,user_id,balance_before,balance_after) VALUES (?,?,?,?,?)",
        (str(refund_id), str(grant_id), int(user_id), int(balance_before), after),
    )
    async with db.execute(
        "UPDATE chest_key_accounts_v1 SET balance=?,updated_at=CLOCK_TIMESTAMP() "
        "WHERE user_id=? AND balance=? RETURNING 1",
        (after, int(user_id), int(balance_before)),
    ) as cursor:
        if not await cursor.fetchone():
            raise RuntimeError("Refund lost its guarded key-balance update.")
    return after
