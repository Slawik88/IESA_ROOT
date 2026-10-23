"""Casino v1 storage: chip wallets, rounds and Мора → chips purchases. Rules: core/casino_v1.py."""
from __future__ import annotations

import json

_TODAY = "(NOW() AT TIME ZONE 'UTC')::date"


def _load(value):
    return json.loads(value) if isinstance(value, str) else value


async def ensure_tables(db) -> None:
    # Concurrent application workers may initialize the cashout schema together.
    # PostgreSQL's IF NOT EXISTS alone does not serialize type/index creation.
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(hashtextextended('ensure_tables:casino_v1', 0))")
        await _ensure_tables_unlocked(db)


async def _ensure_tables_unlocked(db) -> None:
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
    await db.execute("ALTER TABLE casino_v1_wallets ADD COLUMN IF NOT EXISTS redeemable_chips BIGINT NOT NULL DEFAULT 0 CHECK (redeemable_chips >= 0 AND redeemable_chips <= chips)")
    await db.execute("ALTER TABLE casino_v1_wallets ADD COLUMN IF NOT EXISTS wallet_version INTEGER NOT NULL DEFAULT 1")
    await db.execute("CREATE INDEX IF NOT EXISTS casino_v1_rounds_week ON casino_v1_rounds(created_at, payout DESC)")
    await db.execute("CREATE INDEX IF NOT EXISTS casino_v1_rounds_user_recent ON casino_v1_rounds(user_id, created_at DESC)")
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
    await db.execute("""
        CREATE TABLE IF NOT EXISTS casino_v1_withdrawals (
            id TEXT PRIMARY KEY, user_id BIGINT NOT NULL, action_id TEXT NOT NULL,
            chips BIGINT NOT NULL CHECK(chips > 0), mora BIGINT NOT NULL CHECK(mora > 0),
            operation_id TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id,action_id)
        )
    """)


    # Rolling deployments can still route a request to an old worker. Fence its
    # entire transaction before it can mix the legacy 10:1 wallet with cashout.
    # Creating the trigger also waits for already-writing legacy transactions.
    await db.execute("""CREATE OR REPLACE FUNCTION casino_v1_require_current_writer()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF current_setting('predvestnik.casino_wallet_version', true) IS DISTINCT FROM '2' THEN
                RAISE EXCEPTION 'Casino writer must support separate cashout funds' USING ERRCODE='55000';
            END IF;
            RETURN NEW;
        END $$""")
    await db.execute("""DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='casino_v1_wallets'::regclass
                       AND tgname='casino_v1_current_writer') THEN
            CREATE TRIGGER casino_v1_current_writer BEFORE INSERT OR UPDATE ON casino_v1_wallets
            FOR EACH ROW EXECUTE FUNCTION casino_v1_require_current_writer();
        END IF;
    END $$""")


async def lock_wallet(db, user_id: int) -> dict:
    """Create on first use, then lock the row for the caller's transaction."""
    if not db.connection.is_in_transaction():
        raise RuntimeError("Casino wallet writes require a transaction")
    await db.execute("SELECT set_config('predvestnik.casino_wallet_version', '2', true)")
    await db.execute("INSERT INTO casino_v1_wallets(user_id,wallet_version) VALUES (?,2) ON CONFLICT (user_id) DO NOTHING", (int(user_id),))
    async with db.execute(
        f"SELECT *, {_TODAY} AS today FROM casino_v1_wallets WHERE user_id=? FOR UPDATE", (int(user_id),)
    ) as cursor:
        row = dict(await cursor.fetchone())
    if row['wallet_version'] < 2:
        # Old gifts were not individually receipted. Cap compensation by BOTH current chips / old rate
        # and actual historical Mora purchases: no tenfold conversion and no grant to free-only accounts.
        async with db.execute("SELECT COALESCE(SUM(mora),0) FROM casino_v1_purchases WHERE user_id=?", (int(user_id),)) as cur:
            principal = int((await cur.fetchone())[0])
        row['redeemable_chips'] = min(int(row['chips']) // 10, principal)
        await db.execute("UPDATE casino_v1_wallets SET redeemable_chips=?,wallet_version=2 WHERE user_id=?", (row['redeemable_chips'],int(user_id)))
        row['wallet_version'] = 2
    return row


async def wallet(db, user_id: int) -> dict | None:
    async with db.execute(f"""SELECT w.*, {_TODAY} AS today,
        CASE WHEN wallet_version<2 THEN LEAST(chips/10,(SELECT COALESCE(SUM(mora),0) FROM casino_v1_purchases p WHERE p.user_id=w.user_id))
             ELSE redeemable_chips END AS available_redeemable
        FROM casino_v1_wallets w WHERE user_id=?""", (int(user_id),)) as cursor:
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
        f"UPDATE casino_v1_wallets SET chips=chips+?, redeemable_chips=redeemable_chips+?, bought_today=CASE WHEN buy_day={_TODAY} THEN bought_today ELSE 0 END+?, "
        f"buy_day={_TODAY}, updated_at=NOW() WHERE user_id=? RETURNING chips", (int(chips), int(chips), int(chips), int(user_id)),
    ) as cursor:
        return int((await cursor.fetchone())[0])


async def settle_round(db, user_id: int, stake: int, paid: int, funds: str = 'bonus') -> int:
    """Debit the stake and credit the payout in one statement; the CHECK refuses a negative balance."""
    real = funds == 'redeemable'
    change = 'redeemable_chips=redeemable_chips-?+?, ' if real else ''
    available = 'redeemable_chips' if real else '(chips-redeemable_chips)'
    args = (int(stake),int(paid)) + ((int(stake),int(paid)) if real else ()) + (int(stake),int(paid),int(user_id),int(stake))
    async with db.execute("UPDATE casino_v1_wallets SET chips=chips-?+?, " + change +
        "total_staked=total_staked+?, total_paid=total_paid+?, updated_at=NOW() WHERE user_id=? AND " + available + ">=? RETURNING chips", args) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else -1


async def withdraw_chips(db, user_id: int, chips: int) -> int:
    async with db.execute("UPDATE casino_v1_wallets SET chips=chips-?,redeemable_chips=redeemable_chips-?,updated_at=NOW() "
                          "WHERE user_id=? AND redeemable_chips>=? RETURNING chips", (chips,chips,int(user_id),chips)) as cur:
        row = await cur.fetchone()
    return int(row[0]) if row else -1


async def find_withdrawal(db, user_id: int, action_id: str) -> dict | None:
    async with db.execute("SELECT * FROM casino_v1_withdrawals WHERE user_id=? AND action_id=?", (int(user_id),action_id)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def insert_withdrawal(db, *, withdrawal_id: str, user_id: int, action_id: str, chips: int, operation_id: str) -> None:
    await db.execute("INSERT INTO casino_v1_withdrawals(id,user_id,action_id,chips,mora,operation_id) VALUES(?,?,?,?,?,?)",
                     (withdrawal_id,int(user_id),action_id,chips,chips,operation_id))


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
        "SELECT id,game,stake,mult,payout,detail,created_at FROM casino_v1_rounds WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT ?",
        (int(user_id), int(limit)),
    ) as cursor:
        rows = [dict(r) for r in await cursor.fetchall()]
    for row in rows:
        row["detail"] = _load(row["detail"])
    return rows


async def achievement_stats(db, user_id: int) -> dict:
    """Read owned, settled rounds only; no new counters, grants or history migration."""
    async with db.execute("""
        SELECT COUNT(*) AS rounds,
               COUNT(DISTINCT game) FILTER (WHERE game IN ('slots','wheel','dice')) AS games,
               COUNT(*) FILTER (WHERE game='slots' AND detail#>>'{reels,0}' IN ('fehu','raido','thurs','comet','herald')
                   AND detail#>>'{reels,0}'=detail#>>'{reels,1}'
                   AND detail#>>'{reels,1}'=detail#>>'{reels,2}') AS triples,
               COUNT(*) FILTER (WHERE game='wheel' AND payout>stake) AS wheel_wins,
               COUNT(*) FILTER (WHERE game='dice' AND payout>stake) AS dice_wins,
               COALESCE(MAX(mult),0) AS best_mult
        FROM casino_v1_rounds WHERE user_id=?
    """, (int(user_id),)) as cursor:
        return dict(await cursor.fetchone())


async def week_wins(db, limit: int = 10) -> list[dict]:
    """Biggest single wins of the ISO week (UTC), one row per player: «Удача недели»."""
    async with db.execute(
        "SELECT DISTINCT ON (user_id) user_id,game,stake,mult,payout FROM casino_v1_rounds "
        "WHERE created_at>=date_trunc('week', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AND mult>=500 "
        "ORDER BY user_id,payout DESC,created_at", (),
    ) as cursor:
        rows = [dict(r) for r in await cursor.fetchall()]
    return sorted(rows, key=lambda r: (-int(r["payout"]), int(r["user_id"])))[:limit]
