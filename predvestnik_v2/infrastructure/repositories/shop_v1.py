"""Append-only receipts of the shop screen (ECO-04 PR-B).

Only Polish writes here. Key purchases keep their receipts in chest_key_offer_purchases_v1
and exchanges in the economy ledger; this module only reads those to tell which store
already owns an action id.
"""
from __future__ import annotations

import json
from typing import Any


async def ensure_tables(db) -> None:
    # Hot paths call this on every request: a catalog lookup is cheap, DDL is not.
    async with db.execute("SELECT to_regclass('shop_purchases_v1') IS NOT NULL AND EXISTS("
                          "SELECT 1 FROM pg_trigger WHERE tgname='shop_purchases_v1_append_only')") as cursor:
        if (await cursor.fetchone())[0]:
            return
    await db.execute("""
        CREATE TABLE IF NOT EXISTS shop_purchases_v1 (
            id TEXT PRIMARY KEY, user_id BIGINT NOT NULL, action_id TEXT NOT NULL,
            item_id TEXT NOT NULL CHECK(item_id IN ('ess_polish')),
            request_hash TEXT NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
            shop_version TEXT NOT NULL, catalog_digest TEXT NOT NULL CHECK(catalog_digest ~ '^[0-9a-f]{64}$'),
            price JSONB NOT NULL, gives JSONB NOT NULL,
            economy_operation_id TEXT NOT NULL UNIQUE REFERENCES economic_operations(id) ON DELETE RESTRICT,
            purchased_on DATE NOT NULL, purchased_week DATE NOT NULL CHECK(EXTRACT(ISODOW FROM purchased_week) = 1),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(), UNIQUE(user_id,action_id)
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS ix_shop_purchases_v1_limits "
        "ON shop_purchases_v1(user_id,item_id,purchased_week)"
    )
    await db.execute("""
        CREATE OR REPLACE FUNCTION reject_shop_history_rewrite_v1()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'shop purchase history is append-only';
        END;
        $$
    """)
    await db.execute("DROP TRIGGER IF EXISTS shop_purchases_v1_append_only ON shop_purchases_v1")
    await db.execute("""
        CREATE TRIGGER shop_purchases_v1_append_only
        BEFORE UPDATE OR DELETE ON shop_purchases_v1
        FOR EACH ROW EXECUTE FUNCTION reject_shop_history_rewrite_v1()
    """)
    await db.commit()


async def lock_user(db, user_id: int) -> None:
    # Same advisory key as chests and the exchange: one player's purchases are serialised across all three.
    async with db.execute("SELECT pg_advisory_xact_lock(?)", (int(user_id),)) as cursor:
        await cursor.fetchone()


async def window(db) -> tuple[Any, Any, Any]:
    """The UTC day, the Monday of the UTC ISO week and the UTC time, from one CLOCK_TIMESTAMP read."""
    async with db.execute(
        "SELECT (t AT TIME ZONE 'UTC')::date, date_trunc('week', t AT TIME ZONE 'UTC')::date, t AT TIME ZONE 'UTC' "
        "FROM (SELECT CLOCK_TIMESTAMP() AS t) now_utc"
    ) as cursor:
        row = await cursor.fetchone()
    return row[0], row[1], row[2]


async def find_purchase(db, *, user_id: int, action_id: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT * FROM shop_purchases_v1 WHERE user_id=? AND action_id=?", (int(user_id), str(action_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def purchases_in_week(db, *, user_id: int, item_id: str, week: Any) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM shop_purchases_v1 WHERE user_id=? AND item_id=? AND purchased_week=?",
        (int(user_id), str(item_id), week),
    ) as cursor:
        return int((await cursor.fetchone())[0])


async def create_purchase(
    db, *, purchase_id: str, user_id: int, action_id: str, item_id: str, request_hash: str,
    shop_version: str, catalog_digest: str, price: dict, gives: dict, economy_operation_id: str,
    day: Any, week: Any,
) -> None:
    await db.execute(
        "INSERT INTO shop_purchases_v1(id,user_id,action_id,item_id,request_hash,shop_version,catalog_digest,"
        "price,gives,economy_operation_id,purchased_on,purchased_week) "
        "VALUES (?,?,?,?,?,?,?,?::jsonb,?::jsonb,?,?,?)",
        (str(purchase_id), int(user_id), str(action_id), str(item_id), request_hash, shop_version, catalog_digest,
         json.dumps(price, sort_keys=True), json.dumps(gives, sort_keys=True), str(economy_operation_id), day, week),
    )


async def action_owner(db, *, user_id: int, action_id: str) -> str | None:
    """Which store already holds this action id: 'polish', 'key', 'exchange', 'other' or None."""
    if await find_purchase(db, user_id=user_id, action_id=action_id):
        return "polish"
    async with db.execute(
        "SELECT 1 FROM chest_key_offer_purchases_v1 WHERE user_id=? AND action_id=?", (int(user_id), str(action_id)),
    ) as cursor:
        if await cursor.fetchone():
            return "key"
    async with db.execute(
        "SELECT reason_code FROM economic_operations WHERE user_id=? AND idempotency_key=?",
        (int(user_id), str(action_id)),
    ) as cursor:
        row = await cursor.fetchone()
    if row:
        return "exchange" if str(row[0]).startswith("zarniki_exchange_") else "other"
    return None
