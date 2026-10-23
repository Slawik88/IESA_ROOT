"""Casino v1 storage: chip wallets, rounds and Мора → chips purchases. Rules: core/casino_v1.py."""
from __future__ import annotations

import json

_TODAY = "(NOW() AT TIME ZONE 'UTC')::date"


def _load(value):
    return json.loads(value) if isinstance(value, str) else value


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS casino_v1_wallets (
            user_id BIGINT PRIMARY KEY,
            chips BIGINT NOT NULL DEFAULT 0 CHECK (chips >= 0),
            gift_day DATE NULL,
            buy_day DATE NULL,
            bought_today BIGINT NOT NULL DEFAULT 0 CHECK (bought_today >= 0),
            total_staked BIGINT NOT NULL DEFAULT 0,
            total_paid BIGINT NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS casino_v1_rounds (
            id TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            action_id TEXT NOT NULL,
            game TEXT NOT NULL,
            stake BIGINT NOT NULL CHECK (stake > 0),
            mult INTEGER NOT NULL CHECK (mult >= 0),
            payout BIGINT NOT NULL CHECK (payout >= 0),
            detail JSONB NOT NULL,
            chips_after BIGINT NOT NULL,
            policy_version TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, action_id)
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS casino_v1_rounds_week ON casino_v1_rounds(created_at, payout DESC)")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS casino_v1_purchases (
            id TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            action_id TEXT NOT NULL,
            mora BIGINT NOT NULL CHECK (mora > 0),
            chips BIGINT NOT NULL CHECK (chips > 0),
            operation_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, action_id)
        )
    """)


async def lock_wallet(db, user_id: int) -> dict:
    """Create on first use, then lock the row for the caller's transaction."""
    await db.execute("INSERT INTO casino_v1_wallets(user_id) VALUES (?) ON CONFLICT (user_id) DO NOTHING", (int(user_id),))
    async with db.execute(
        f"SELECT *, {_TODAY} AS today FROM casino_v1_wallets WHERE user_id=? FOR UPDATE", (int(user_id),)
    ) as cursor:
        return dict(await cursor.fetchone())


async def wallet(db, user_id: int) -> dict | None:
    async with db.execute(f"SELECT *, {_TODAY} AS today FROM casino_v1_wallets WHERE user_id=?", (int(user_id),)) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def today(db):
    async with db.execute(f"SELECT {_TODAY}") as cursor:
        return (await cursor.fetchone())[0]


async def claim_gift(db, user_id: int, amount: int) -> int:
    async with db.execute(
        f"UPDATE casino_v1_wallets SET chips=chips+?, gift_day={_TODAY}, updated_at=NOW() "
        f"WHERE user_id=? AND (gift_day IS NULL OR gift_day<{_TODAY}) RETURNING chips", (int(amount), int(user_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else -1


async def add_bought(db, user_id: int, chips: int) -> int:
    async with db.execute(
        f"UPDATE casino_v1_wallets SET chips=chips+?, bought_today=CASE WHEN buy_day={_TODAY} THEN bought_today ELSE 0 END+?, "
        f"buy_day={_TODAY}, updated_at=NOW() WHERE user_id=? RETURNING chips", (int(chips), int(chips), int(user_id)),
    ) as cursor:
        return int((await cursor.fetchone())[0])


async def settle_round(db, user_id: int, stake: int, paid: int) -> int:
    """Debit the stake and credit the payout in one statement; the CHECK refuses a negative balance."""
    async with db.execute(
        "UPDATE casino_v1_wallets SET chips=chips-?+?, total_staked=total_staked+?, total_paid=total_paid+?, "
        "updated_at=NOW() WHERE user_id=? AND chips>=? RETURNING chips",
        (int(stake), int(paid), int(stake), int(paid), int(user_id), int(stake)),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else -1


async def insert_round(db, *, round_id: str, user_id: int, action_id: str, game: str, stake: int, mult: int,
                       payout: int, detail: dict, chips_after: int, policy_version: str) -> None:
    await db.execute(
        "INSERT INTO casino_v1_rounds(id,user_id,action_id,game,stake,mult,payout,detail,chips_after,policy_version) "
        "VALUES (?,?,?,?,?,?,?,?::jsonb,?,?)",
        (round_id, int(user_id), action_id, game, int(stake), int(mult), int(payout), json.dumps(detail),
         int(chips_after), policy_version),
    )


async def find_round(db, user_id: int, action_id: str) -> dict | None:
    async with db.execute("SELECT * FROM casino_v1_rounds WHERE user_id=? AND action_id=?", (int(user_id), action_id)) as cursor:
        row = await cursor.fetchone()
    if not row:
        return None
    row = dict(row)
    row["detail"] = _load(row["detail"])
    return row


async def insert_purchase(db, *, purchase_id: str, user_id: int, action_id: str, mora: int, chips: int,
                          operation_id: str) -> None:
    await db.execute(
        "INSERT INTO casino_v1_purchases(id,user_id,action_id,mora,chips,operation_id) VALUES (?,?,?,?,?,?)",
        (purchase_id, int(user_id), action_id, int(mora), int(chips), operation_id),
    )


async def find_purchase(db, user_id: int, action_id: str) -> dict | None:
    async with db.execute("SELECT * FROM casino_v1_purchases WHERE user_id=? AND action_id=?", (int(user_id), action_id)) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def recent_rounds(db, user_id: int, limit: int = 8) -> list[dict]:
    async with db.execute(
        "SELECT game,stake,mult,payout,detail,created_at FROM casino_v1_rounds WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
        (int(user_id), int(limit)),
    ) as cursor:
        rows = [dict(r) for r in await cursor.fetchall()]
    for row in rows:
        row["detail"] = _load(row["detail"])
    return rows


async def week_wins(db, limit: int = 10) -> list[dict]:
    """Biggest single wins of the ISO week (UTC), one row per player: «Удача недели»."""
    async with db.execute(
        "SELECT DISTINCT ON (user_id) user_id,game,stake,mult,payout FROM casino_v1_rounds "
        "WHERE created_at>=date_trunc('week', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AND mult>=500 "
        "ORDER BY user_id,payout DESC,created_at", (),
    ) as cursor:
        rows = [dict(r) for r in await cursor.fetchall()]
    return sorted(rows, key=lambda r: (-int(r["payout"]), int(r["user_id"])))[:limit]
