"""Quota storage for the versioned Zarniki conversion service."""
from __future__ import annotations


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS zarniki_exchange_usage_v1 (
            user_id BIGINT NOT NULL,
            utc_date DATE NOT NULL,
            zarniki_spent INTEGER NOT NULL DEFAULT 0 CHECK(zarniki_spent >= 0),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id, utc_date)
        )
    """)


async def lock_user(db, user_id: int) -> None:
    async with db.execute("SELECT pg_advisory_xact_lock(?)", (int(user_id),)) as cursor:
        await cursor.fetchone()


async def usage_today(db, user_id: int) -> int:
    async with db.execute(
        "SELECT zarniki_spent FROM zarniki_exchange_usage_v1 "
        "WHERE user_id=? AND utc_date=CURRENT_DATE FOR UPDATE",
        (int(user_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def add_usage_today(db, user_id: int, amount: int) -> int:
    async with db.execute(
        "INSERT INTO zarniki_exchange_usage_v1(user_id,utc_date,zarniki_spent) "
        "VALUES (?,CURRENT_DATE,?) ON CONFLICT(user_id,utc_date) DO UPDATE "
        "SET zarniki_spent=zarniki_exchange_usage_v1.zarniki_spent+EXCLUDED.zarniki_spent,updated_at=NOW() "
        "RETURNING zarniki_spent",
        (int(user_id), int(amount)),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise RuntimeError("Exchange quota was not recorded")
    return int(row[0])
