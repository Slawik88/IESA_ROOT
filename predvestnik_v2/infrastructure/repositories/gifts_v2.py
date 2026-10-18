"""Gift receipts and the shelf showcase (ECO-04 PR-C).

``gift_sends_v2`` is append-only: one row per gift sent, with tier, gift, note, sender,
receiver, price and the ledger operation that paid for it. ``gift_pins_v2`` is the
recipient's showcase (up to three received gifts) and is the only mutable part.
Limits read the receipts of one UTC day under the sender's advisory lock.
"""
from __future__ import annotations

import json
from typing import Any

from infrastructure.repositories import shop_v1 as shop_repo


async def ensure_tables(db) -> None:
    if await _schema_ready(db):
        return
    # Request handlers reach lazy schema installation at the same moment after a
    # rollout.  PostgreSQL does not serialize concurrent DDL: CREATE OR REPLACE
    # FUNCTION answered "tuple concurrently updated" (production, 2026-10-18) and the
    # former DROP+CREATE trigger collided with "already exists".
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(hashtextextended('ensure_tables:gifts_v2', 0))")
        if not await _schema_ready(db):
            await _ensure_tables_unlocked(db)


async def _schema_ready(db) -> bool:
    # Hot paths call this on every request: a catalog lookup is cheap, DDL is not.
    async with db.execute("SELECT to_regclass('gift_pins_v2') IS NOT NULL AND EXISTS("
                          "SELECT 1 FROM pg_trigger WHERE tgname='gift_sends_v2_append_only')") as cursor:
        return bool((await cursor.fetchone())[0])


async def _ensure_tables_unlocked(db) -> None:
    # gift_id is a pattern, not a list: a new gift in core/gifts_v2.py needs no constraint migration.
    # Named CHECKs mirror core/gifts_v2.py (TIERS, NOTE_MAX). This fast path never alters an existing table:
    # changing either constant needs an explicit ALTER TABLE ... DROP/ADD CONSTRAINT gift_sends_v2_tier_range / _note_length.
    await db.execute("""
        CREATE TABLE IF NOT EXISTS gift_sends_v2 (
            id TEXT PRIMARY KEY CHECK(id ~ '^[0-9a-f]{32}$'),
            sender_id BIGINT NOT NULL, receiver_id BIGINT NOT NULL, action_id TEXT NOT NULL,
            gift_id TEXT NOT NULL CHECK(gift_id ~ '^gift_[a-z0-9_]{1,40}$'),
            tier SMALLINT NOT NULL CONSTRAINT gift_sends_v2_tier_range CHECK(tier BETWEEN 1 AND 4),
            note TEXT NULL CONSTRAINT gift_sends_v2_note_length CHECK(note IS NULL OR char_length(note) BETWEEN 1 AND 60),
            request_hash TEXT NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
            gifts_version TEXT NOT NULL, catalog_digest TEXT NOT NULL CHECK(catalog_digest ~ '^[0-9a-f]{64}$'),
            price JSONB NOT NULL, marriage_id INTEGER NULL,
            economy_operation_id TEXT NOT NULL UNIQUE REFERENCES economic_operations(id) ON DELETE RESTRICT,
            sent_on DATE NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(),
            UNIQUE(sender_id, action_id), CHECK(sender_id <> receiver_id)
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS ix_gift_sends_v2_sender_day ON gift_sends_v2(sender_id, sent_on, receiver_id)")
    await db.execute("CREATE INDEX IF NOT EXISTS ix_gift_sends_v2_receiver ON gift_sends_v2(receiver_id, created_at DESC)")
    await db.execute("""
        CREATE OR REPLACE FUNCTION reject_gift_history_rewrite_v2()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'gift send history is append-only';
        END;
        $$
    """)
    # Cold start only: two first requests after a restart used to collide on the
    # DROP+CREATE pair (production, 2026-10-18).  Guard on the catalog and swallow
    # a create/create race: the trigger exists exactly once either way.
    await db.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgname='gift_sends_v2_append_only'
                  AND tgrelid='gift_sends_v2'::regclass AND NOT tgisinternal
            ) THEN
                BEGIN
                    CREATE TRIGGER gift_sends_v2_append_only
                    BEFORE UPDATE OR DELETE ON gift_sends_v2
                    FOR EACH ROW EXECUTE FUNCTION reject_gift_history_rewrite_v2();
                EXCEPTION WHEN duplicate_object THEN NULL;
                END;
            END IF;
        END $$
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS gift_pins_v2 (
            send_id TEXT PRIMARY KEY REFERENCES gift_sends_v2(id) ON DELETE RESTRICT,
            receiver_id BIGINT NOT NULL, pinned_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP()
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS ix_gift_pins_v2_receiver ON gift_pins_v2(receiver_id)")
    await db.commit()


async def lock_user(db, user_id: int) -> None:
    """Same advisory key as the shop, chests and the exchange: one player's spending is serialised across all of them."""
    await shop_repo.lock_user(db, user_id)


async def window(db) -> tuple[Any, Any, Any]:
    """The UTC day, the Monday of the UTC week and the UTC time, from one CLOCK_TIMESTAMP read."""
    return await shop_repo.window(db)


async def partner_of(db, user_id: int, *, lock: bool = False) -> dict[str, Any] | None:
    """The live marriage of this player (global, one per player): marriage id and partner id.
    ``lock`` holds the marriage row for share until the transaction ends, so a divorce cannot commit in between."""
    async with db.execute(
        "SELECT m.id, m.user1_id, m.user2_id FROM marriage_members mm JOIN marriages m ON m.id = mm.marriage_id "
        "WHERE mm.user_id = ? AND m.ended_at IS NULL ORDER BY m.marriage_date DESC LIMIT 1"
        + (" FOR SHARE OF m" if lock else ""),
        (int(user_id),),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return None
    a, b = int(row["user1_id"]), int(row["user2_id"])
    partner = b if a == int(user_id) else a
    return {"marriage_id": int(row["id"]), "partner_id": partner} if partner != int(user_id) else None


async def find_send(db, *, sender_id: int, action_id: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT * FROM gift_sends_v2 WHERE sender_id=? AND action_id=?", (int(sender_id), str(action_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def get_send(db, send_id: str) -> dict[str, Any] | None:
    async with db.execute("SELECT * FROM gift_sends_v2 WHERE id=?", (str(send_id),)) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def sent_today(db, *, sender_id: int, day: Any, receiver_id: int | None = None) -> int:
    sql = "SELECT COUNT(*) FROM gift_sends_v2 WHERE sender_id=? AND sent_on=?"
    params: tuple = (int(sender_id), day)
    if receiver_id is not None:
        sql += " AND receiver_id=?"
        params += (int(receiver_id),)
    async with db.execute(sql, params) as cursor:
        return int((await cursor.fetchone())[0])


async def create_send(
    db, *, send_id: str, sender_id: int, receiver_id: int, action_id: str, gift_id: str, tier: int,
    note: str | None, request_hash: str, gifts_version: str, catalog_digest: str, price: dict,
    marriage_id: int | None, economy_operation_id: str, day: Any,
) -> None:
    await db.execute(
        "INSERT INTO gift_sends_v2(id,sender_id,receiver_id,action_id,gift_id,tier,note,request_hash,gifts_version,"
        "catalog_digest,price,marriage_id,economy_operation_id,sent_on) VALUES (?,?,?,?,?,?,?,?,?,?,?::jsonb,?,?,?)",
        (str(send_id), int(sender_id), int(receiver_id), str(action_id), str(gift_id), int(tier), note, request_hash,
         gifts_version, catalog_digest, json.dumps(price, sort_keys=True), marriage_id, str(economy_operation_id), day),
    )


async def counts(db, user_id: int) -> dict[str, int]:
    async with db.execute(
        "SELECT (SELECT COUNT(*) FROM gift_sends_v2 WHERE receiver_id=?), (SELECT COUNT(*) FROM gift_sends_v2 WHERE sender_id=?)",
        (int(user_id), int(user_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return {"received": int(row[0]), "sent": int(row[1])}


async def received_by_gift(db, user_id: int) -> list[dict[str, Any]]:
    """Per gift kind: how many received and the newest one (for the shelf slots)."""
    async with db.execute(
        "SELECT gift_id, COUNT(*) AS n, MAX(created_at) AS last_at FROM gift_sends_v2 WHERE receiver_id=? GROUP BY gift_id",
        (int(user_id),),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def history(
    db, *, user_id: int, box: str, tier: int | None = None, gift_id: str | None = None, limit: int = 50,
    before: Any = None,
) -> list[dict[str, Any]]:
    column = "receiver_id" if box == "received" else "sender_id"
    sql = (f"SELECT s.*, (p.send_id IS NOT NULL) AS pinned FROM gift_sends_v2 s "
           f"LEFT JOIN gift_pins_v2 p ON p.send_id = s.id WHERE s.{column}=?")
    params: tuple = (int(user_id),)
    if tier is not None:
        sql += " AND s.tier=?"
        params += (int(tier),)
    if gift_id is not None:
        sql += " AND s.gift_id=?"
        params += (str(gift_id),)
    sql += " ORDER BY s.created_at DESC, s.id DESC LIMIT ?"
    params += (int(limit),)
    async with db.execute(sql, params) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def pinned(db, user_id: int) -> list[dict[str, Any]]:
    async with db.execute(
        "SELECT s.*, TRUE AS pinned FROM gift_pins_v2 p JOIN gift_sends_v2 s ON s.id = p.send_id "
        "WHERE p.receiver_id=? AND s.receiver_id=? ORDER BY p.pinned_at, s.id",
        (int(user_id), int(user_id)),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def pin(db, *, user_id: int, send_id: str) -> None:
    await db.execute(
        "INSERT INTO gift_pins_v2(send_id, receiver_id) VALUES (?, ?) ON CONFLICT(send_id) DO NOTHING",
        (str(send_id), int(user_id)),
    )


async def unpin(db, *, user_id: int, send_id: str) -> None:
    await db.execute("DELETE FROM gift_pins_v2 WHERE send_id=? AND receiver_id=?", (str(send_id), int(user_id)))


async def top_tier_latest(db, user_id: int, tier: int) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT gift_id FROM gift_sends_v2 WHERE receiver_id=? AND tier=? ORDER BY created_at DESC, id DESC LIMIT 1",
        (int(user_id), int(tier)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None
