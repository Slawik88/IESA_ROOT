"""Storage for Skins V3: owned skins with their current tier, the equipped skin, and the Essence account.

Essence has its own account and append-only ledger (same idea as echo_shards_v1): it never touches the
four-currency economy ledger, so a bug here cannot change Mora, Diamonds, Dark Mora or Zarniki.
"""
from __future__ import annotations


async def ensure_tables(db) -> None:
    # Hot read paths call this on every request: a catalog lookup is cheap, DDL is not.
    async with db.execute("SELECT to_regclass('skins_v3_owned') IS NOT NULL AND to_regclass('skins_v3_equipped') IS NOT NULL "
                          "AND to_regclass('skins_v3_essence_accounts') IS NOT NULL AND to_regclass('skins_v3_essence_ledger') IS NOT NULL") as c:
        if (await c.fetchone())[0]:
            return
    await db.execute("""
        CREATE TABLE IF NOT EXISTS skins_v3_owned (
            user_id BIGINT NOT NULL,
            skin_id TEXT NOT NULL,
            tier TEXT NOT NULL DEFAULT 'D',
            acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            upgraded_at TIMESTAMPTZ,
            PRIMARY KEY(user_id, skin_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS skins_v3_equipped (
            user_id BIGINT PRIMARY KEY,
            skin_id TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS skins_v3_essence_accounts (
            user_id BIGINT PRIMARY KEY,
            balance BIGINT NOT NULL DEFAULT 0 CHECK(balance >= 0),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS skins_v3_essence_ledger (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            delta BIGINT NOT NULL CHECK(delta <> 0),
            balance_before BIGINT NOT NULL CHECK(balance_before >= 0),
            balance_after BIGINT NOT NULL CHECK(balance_after >= 0 AND balance_after = balance_before + delta),
            reason TEXT NOT NULL,
            reference TEXT,
            idempotency_key TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, idempotency_key)
        )
    """)


async def owned(db, user_id: int) -> dict[str, str]:
    async with db.execute("SELECT skin_id, tier FROM skins_v3_owned WHERE user_id=? ORDER BY acquired_at, skin_id", (int(user_id),)) as c:
        return {str(r[0]): str(r[1]) for r in await c.fetchall()}


async def owned_tier_locked(db, user_id: int, skin_id: str) -> str | None:
    async with db.execute("SELECT tier FROM skins_v3_owned WHERE user_id=? AND skin_id=? FOR UPDATE", (int(user_id), str(skin_id))) as c:
        row = await c.fetchone()
    return str(row[0]) if row else None


async def grant(db, user_id: int, skin_id: str) -> bool:
    async with db.execute(
        "INSERT INTO skins_v3_owned(user_id, skin_id, tier) VALUES (?,?, 'D') ON CONFLICT DO NOTHING RETURNING 1",
        (int(user_id), str(skin_id)),
    ) as c:
        return await c.fetchone() is not None


async def remove(db, user_id: int, skin_id: str) -> bool:
    """Take a skin away (console only): the ownership row goes, and so does the equip row that pointed at it. Spent Essence is not returned."""
    async with db.execute("DELETE FROM skins_v3_owned WHERE user_id=? AND skin_id=? RETURNING 1", (int(user_id), str(skin_id))) as c:
        removed = await c.fetchone() is not None
    await db.execute("DELETE FROM skins_v3_equipped WHERE user_id=? AND skin_id=?", (int(user_id), str(skin_id)))
    return removed


async def holders(db, skin_id: str) -> list[dict]:
    """Everyone who owns a skin, oldest first, with their tier and name: the console checks a personal skin has not gone to two people."""
    async with db.execute(
        "SELECT o.user_id, o.tier, o.acquired_at, u.user_tg_username, (e.skin_id IS NOT NULL) FROM skins_v3_owned o LEFT JOIN users u ON u.user_tg_id=o.user_id "
        "LEFT JOIN skins_v3_equipped e ON e.user_id=o.user_id AND e.skin_id=o.skin_id WHERE o.skin_id=? ORDER BY o.acquired_at, o.user_id", (str(skin_id),)) as c:
        return [{"user_id": int(r[0]), "tier": str(r[1]), "since": r[2].isoformat() if r[2] else None, "username": r[3], "equipped": bool(r[4])} for r in await c.fetchall()]


async def set_tier(db, user_id: int, skin_id: str, tier: str) -> None:
    await db.execute("UPDATE skins_v3_owned SET tier=?, upgraded_at=NOW() WHERE user_id=? AND skin_id=?", (str(tier), int(user_id), str(skin_id)))


async def equipped(db, user_id: int) -> str | None:
    async with db.execute("SELECT skin_id FROM skins_v3_equipped WHERE user_id=?", (int(user_id),)) as c:
        row = await c.fetchone()
    return str(row[0]) if row else None


async def equipped_batch(db, user_ids: list[int]) -> dict[int, tuple[str, str]]:
    """{user_id: (skin_id, tier)} for players who wear a skin they own."""
    ids = [int(u) for u in user_ids]
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    async with db.execute(
        f"SELECT e.user_id, e.skin_id, o.tier FROM skins_v3_equipped e JOIN skins_v3_owned o ON o.user_id=e.user_id AND o.skin_id=e.skin_id WHERE e.user_id IN ({marks})",
        tuple(ids),
    ) as c:
        return {int(r[0]): (str(r[1]), str(r[2])) for r in await c.fetchall()}


async def set_equipped(db, user_id: int, skin_id: str | None) -> None:
    if skin_id is None:
        await db.execute("DELETE FROM skins_v3_equipped WHERE user_id=?", (int(user_id),))
        return
    await db.execute(
        "INSERT INTO skins_v3_equipped(user_id, skin_id) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET skin_id=EXCLUDED.skin_id, updated_at=NOW()",
        (int(user_id), str(skin_id)),
    )


async def essence_balance(db, user_id: int) -> int:
    async with db.execute("SELECT balance FROM skins_v3_essence_accounts WHERE user_id=?", (int(user_id),)) as c:
        row = await c.fetchone()
    return int(row[0]) if row else 0


async def essence_apply(db, user_id: int, delta: int, *, reason: str, reference: str | None, idempotency_key: str) -> tuple[bool, int]:
    """Apply one signed Essence change exactly once. Returns (applied, balance_after); a replay returns (False, balance)."""
    await db.execute("INSERT INTO skins_v3_essence_accounts(user_id) VALUES (?) ON CONFLICT DO NOTHING", (int(user_id),))
    async with db.execute("SELECT balance FROM skins_v3_essence_accounts WHERE user_id=? FOR UPDATE", (int(user_id),)) as c:
        before = int((await c.fetchone())[0])
    async with db.execute("SELECT 1 FROM skins_v3_essence_ledger WHERE user_id=? AND idempotency_key=?", (int(user_id), idempotency_key)) as c:
        if await c.fetchone():
            return False, before
    after = before + int(delta)
    if after < 0:
        raise ValueError("insufficient essence")
    await db.execute(
        "INSERT INTO skins_v3_essence_ledger(user_id, delta, balance_before, balance_after, reason, reference, idempotency_key) VALUES (?,?,?,?,?,?,?)",
        (int(user_id), int(delta), before, after, reason, reference, idempotency_key),
    )
    await db.execute("UPDATE skins_v3_essence_accounts SET balance=?, updated_at=NOW() WHERE user_id=?", (after, int(user_id)))
    return True, after
