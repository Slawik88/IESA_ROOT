"""Durable receipts for the current single-product VIP subscription."""
from __future__ import annotations

import json


async def ensure_tables(db) -> None:
    if await _schema_ready(db):
        return
    # Request handlers may reach lazy schema installation concurrently after a
    # rollout. PostgreSQL does not serialize CREATE OR REPLACE FUNCTION, so use
    # one session-scoped installer lock around the complete schema operation.
    await db.execute("SELECT pg_advisory_lock(?)", (91502026,))
    try:
        if not await _schema_ready(db):
            await _ensure_tables_unlocked(db)
    finally:
        await db.execute("SELECT pg_advisory_unlock(?)", (91502026,))


async def _schema_ready(db) -> bool:
    async with db.execute(
        """
        SELECT to_regclass('vip_v2_purchases') IS NOT NULL
           AND to_regclass('vip_v2_preferences') IS NOT NULL
           AND to_regclass('vip_v2_daily_progress') IS NOT NULL
           AND to_regclass('vip_v2_daily_receipts') IS NOT NULL
           AND EXISTS (
               SELECT 1 FROM pg_trigger WHERE tgname='vip_v2_purchases_append_only'
                 AND tgrelid=to_regclass('vip_v2_purchases') AND NOT tgisinternal
           )
           AND EXISTS (
               SELECT 1 FROM pg_trigger WHERE tgname='vip_v2_daily_receipts_append_only'
                 AND tgrelid=to_regclass('vip_v2_daily_receipts') AND NOT tgisinternal
           )
           AND EXISTS (
               SELECT 1 FROM information_schema.columns
               WHERE table_schema=current_schema() AND table_name='vip_v2_preferences'
                 AND column_name='dm_confirmed_at'
           )
           AND EXISTS (
               SELECT 1 FROM information_schema.columns
               WHERE table_schema=current_schema() AND table_name='vip_v2_preferences'
                 AND column_name='dm_disabled_at'
           )
        """
    ) as cursor:
        row = await cursor.fetchone()
    return bool(row and row[0])


async def _ensure_tables_unlocked(db) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS vip_v2_purchases (
            id TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            action_id TEXT NOT NULL,
            package_days INTEGER NOT NULL CHECK (package_days IN (7, 30, 90, 365)),
            price_zarniki INTEGER NOT NULL CHECK (price_zarniki > 0),
            request_json JSONB NOT NULL,
            economy_operation_id TEXT NOT NULL REFERENCES economic_operations(id) ON DELETE RESTRICT,
            expires_at_before TIMESTAMPTZ,
            expires_at_after TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, action_id)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_vip_v2_purchases_user_created "
        "ON vip_v2_purchases(user_id, created_at DESC)"
    )
    await db.execute(
        """
        CREATE OR REPLACE FUNCTION reject_vip_v2_receipt_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'VIP v2 receipts are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    await db.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgname='vip_v2_purchases_append_only'
                  AND tgrelid='vip_v2_purchases'::regclass
            ) THEN
                CREATE TRIGGER vip_v2_purchases_append_only
                BEFORE UPDATE OR DELETE ON vip_v2_purchases
                FOR EACH ROW EXECUTE FUNCTION reject_vip_v2_receipt_mutation();
            END IF;
        END $$
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS vip_v2_preferences (
            user_id BIGINT PRIMARY KEY,
            badge_id TEXT,
            badge_position TEXT NOT NULL DEFAULT 'left'
                CHECK (badge_position IN ('left','right','both','hidden')),
            reminder_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            missed_reminders SMALLINT NOT NULL DEFAULT 0 CHECK (missed_reminders BETWEEN 0 AND 2),
            last_reminder_day DATE,
            dm_confirmed_at TIMESTAMPTZ,
            dm_disabled_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await db.execute("ALTER TABLE vip_v2_preferences ADD COLUMN IF NOT EXISTS missed_reminders SMALLINT NOT NULL DEFAULT 0")
    await db.execute("ALTER TABLE vip_v2_preferences ADD COLUMN IF NOT EXISTS last_reminder_day DATE")
    await db.execute("ALTER TABLE vip_v2_preferences ADD COLUMN IF NOT EXISTS dm_confirmed_at TIMESTAMPTZ")
    await db.execute("ALTER TABLE vip_v2_preferences ADD COLUMN IF NOT EXISTS dm_disabled_at TIMESTAMPTZ")
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS vip_v2_daily_progress (
            user_id BIGINT PRIMARY KEY,
            completed_count INTEGER NOT NULL DEFAULT 0 CHECK (completed_count >= 0),
            last_completed_day DATE,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS vip_v2_daily_receipts (
            user_id BIGINT NOT NULL,
            day_key DATE NOT NULL,
            source_event_id TEXT NOT NULL,
            completion_no INTEGER NOT NULL CHECK (completion_no > 0),
            mora_reward INTEGER NOT NULL CHECK (mora_reward IN (20,120)),
            mora_operation_id TEXT NOT NULL REFERENCES economic_operations(id) ON DELETE RESTRICT,
            chest_key_grant_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, day_key),
            UNIQUE (user_id, source_event_id)
        )
        """
    )
    await db.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgname='vip_v2_daily_receipts_append_only'
                  AND tgrelid='vip_v2_daily_receipts'::regclass
            ) THEN
                CREATE TRIGGER vip_v2_daily_receipts_append_only
                BEFORE UPDATE OR DELETE ON vip_v2_daily_receipts
                FOR EACH ROW EXECUTE FUNCTION reject_vip_v2_receipt_mutation();
            END IF;
        END $$
        """
    )


async def lock_user(db, user_id: int) -> None:
    await db.execute("INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (int(user_id),))
    async with db.execute("SELECT user_tg_id FROM users WHERE user_tg_id=? FOR UPDATE", (int(user_id),)) as cursor:
        if not await cursor.fetchone():
            raise RuntimeError("VIP owner row disappeared")


async def find_purchase(db, *, user_id: int, action_id: str):
    async with db.execute(
        "SELECT * FROM vip_v2_purchases WHERE user_id=? AND action_id=?",
        (int(user_id), action_id),
    ) as cursor:
        return await cursor.fetchone()


async def current_subscription_for_update(db, *, user_id: int):
    async with db.execute(
        "SELECT tier, started_at, expires_at, COALESCE(total_days,0) AS total_days "
        "FROM vip_subscriptions WHERE user_id=? FOR UPDATE",
        (int(user_id),),
    ) as cursor:
        return await cursor.fetchone()


async def extend_subscription(db, *, user_id: int, days: int):
    async with db.execute(
        """
        INSERT INTO vip_subscriptions(user_id,tier,started_at,expires_at,expiry_notified,total_days)
        VALUES (?,'vip',NOW(),NOW()+make_interval(days => ?),FALSE,?)
        ON CONFLICT (user_id) DO UPDATE SET
            tier='vip',
            started_at=CASE WHEN vip_subscriptions.expires_at>NOW()
                            THEN vip_subscriptions.started_at ELSE NOW() END,
            expires_at=GREATEST(vip_subscriptions.expires_at,NOW())+make_interval(days => ?),
            expiry_notified=FALSE,
            total_days=COALESCE(vip_subscriptions.total_days,0)+?
        RETURNING expires_at
        """,
        (int(user_id), int(days), int(days), int(days), int(days)),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise RuntimeError("VIP subscription was not extended")
    return row[0]


async def save_purchase(
    db, *, purchase_id: str, user_id: int, action_id: str, package_days: int,
    price_zarniki: int, economy_operation_id: str, expires_at_before, expires_at_after,
) -> None:
    request = json.dumps(
        {"package_days": int(package_days), "price_zarniki": int(price_zarniki)},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    await db.execute(
        "INSERT INTO vip_v2_purchases "
        "(id,user_id,action_id,package_days,price_zarniki,request_json,economy_operation_id,"
        " expires_at_before,expires_at_after) VALUES (?,?,?,?,?,?::jsonb,?,?,?)",
        (purchase_id, int(user_id), action_id, int(package_days), int(price_zarniki), request,
         economy_operation_id, expires_at_before, expires_at_after),
    )


async def get_preferences(db, *, user_id: int):
    async with db.execute(
        "SELECT badge_id,badge_position,reminder_enabled FROM vip_v2_preferences WHERE user_id=?",
        (int(user_id),),
    ) as cursor:
        return await cursor.fetchone()


async def get_preferences_batch(db, *, user_ids: list[int]) -> dict[int, dict]:
    ids = sorted({int(value) for value in user_ids})
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    async with db.execute(
        f"SELECT user_id,badge_id,badge_position,reminder_enabled "
        f"FROM vip_v2_preferences WHERE user_id IN ({marks})", tuple(ids),
    ) as cursor:
        return {int(row["user_id"]): dict(row) for row in await cursor.fetchall()}


async def save_preferences(
    db, *, user_id: int, badge_id: str | None, badge_position: str, reminder_enabled: bool,
) -> None:
    await db.execute(
        """
        INSERT INTO vip_v2_preferences(user_id,badge_id,badge_position,reminder_enabled,updated_at)
        VALUES (?,?,?,?,NOW())
        ON CONFLICT (user_id) DO UPDATE SET badge_id=EXCLUDED.badge_id,
            badge_position=EXCLUDED.badge_position,
            reminder_enabled=EXCLUDED.reminder_enabled,updated_at=NOW()
        """,
        (int(user_id), badge_id, badge_position, bool(reminder_enabled)),
    )


async def get_daily_progress_for_update(db, *, user_id: int):
    await db.execute(
        "INSERT INTO vip_v2_daily_progress(user_id) VALUES (?) ON CONFLICT DO NOTHING",
        (int(user_id),),
    )
    async with db.execute(
        "SELECT * FROM vip_v2_daily_progress WHERE user_id=? FOR UPDATE", (int(user_id),),
    ) as cursor:
        return await cursor.fetchone()


async def get_daily_progress(db, *, user_id: int):
    async with db.execute(
        "SELECT * FROM vip_v2_daily_progress WHERE user_id=?", (int(user_id),),
    ) as cursor:
        return await cursor.fetchone()


async def find_daily_receipt(db, *, user_id: int, day_key: str):
    async with db.execute(
        "SELECT * FROM vip_v2_daily_receipts WHERE user_id=? AND day_key=?::text::date",
        (int(user_id), day_key),
    ) as cursor:
        return await cursor.fetchone()


async def save_daily_completion(
    db, *, user_id: int, day_key: str, source_event_id: str, completion_no: int,
    mora_reward: int, mora_operation_id: str, chest_key_grant_id: str | None,
) -> None:
    await db.execute(
        "INSERT INTO vip_v2_daily_receipts "
        "(user_id,day_key,source_event_id,completion_no,mora_reward,mora_operation_id,chest_key_grant_id) "
        "VALUES (?,?::text::date,?,?,?,?,?)",
        (int(user_id), day_key, source_event_id, int(completion_no), int(mora_reward),
         mora_operation_id, chest_key_grant_id),
    )
    await db.execute(
        "UPDATE vip_v2_preferences SET missed_reminders=0,updated_at=NOW() WHERE user_id=?",
        (int(user_id),),
    )
    await db.execute(
        "UPDATE vip_v2_daily_progress "
        "SET completed_count=?,last_completed_day=?::text::date,updated_at=NOW() WHERE user_id=?",
        (int(completion_no), day_key, int(user_id)),
    )


async def reminder_candidates(db, *, day_key: str) -> list[dict]:
    async with db.execute(
        """
        SELECT v.user_id
        FROM vip_subscriptions v
        LEFT JOIN vip_v2_preferences p ON p.user_id=v.user_id
        LEFT JOIN vip_v2_daily_receipts r ON r.user_id=v.user_id AND r.day_key=?::text::date
        WHERE v.expires_at>NOW() AND r.user_id IS NULL
          AND COALESCE(p.reminder_enabled,TRUE)=TRUE
          AND p.dm_confirmed_at IS NOT NULL AND p.dm_disabled_at IS NULL
          AND COALESCE(p.missed_reminders,0)<2
          AND (p.last_reminder_day IS NULL OR p.last_reminder_day<?::text::date)
        ORDER BY v.user_id
        LIMIT 500
        """, (day_key, day_key),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def mark_reminder_sent(db, *, user_id: int, day_key: str) -> None:
    await db.execute(
        """
        INSERT INTO vip_v2_preferences(user_id,missed_reminders,last_reminder_day)
        VALUES (?,1,?::text::date)
        ON CONFLICT (user_id) DO UPDATE SET
            missed_reminders=LEAST(2,vip_v2_preferences.missed_reminders+1),
            last_reminder_day=EXCLUDED.last_reminder_day,updated_at=NOW()
        WHERE vip_v2_preferences.last_reminder_day IS NULL
           OR vip_v2_preferences.last_reminder_day<EXCLUDED.last_reminder_day
        """, (int(user_id), day_key),
    )


async def mark_private_contact(db, *, user_id: int) -> None:
    await db.execute(
        """
        INSERT INTO vip_v2_preferences(user_id,dm_confirmed_at,dm_disabled_at,updated_at)
        VALUES (?,NOW(),NULL,NOW())
        ON CONFLICT (user_id) DO UPDATE SET
            dm_confirmed_at=NOW(),dm_disabled_at=NULL,updated_at=NOW()
        """,
        (int(user_id),),
    )


async def mark_private_contact_unreachable(db, *, user_id: int) -> None:
    await db.execute(
        "UPDATE vip_v2_preferences SET dm_disabled_at=NOW(),updated_at=NOW() WHERE user_id=?",
        (int(user_id),),
    )
