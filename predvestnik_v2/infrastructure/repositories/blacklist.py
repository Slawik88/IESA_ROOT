"""
infrastructure/repositories/blacklist.py
Chat blacklist (per-chat) and global blacklist (developer-only).
"""
import aiosqlite
from typing import Optional


# ── Chat blacklist ────────────────────────────────────────────────────────────

async def add_to_chat_blacklist(
    db: aiosqlite.Connection,
    chat_id: int,
    user_id: int,
    reason: Optional[str],
    added_by: int,
) -> None:
    await db.execute(
        """INSERT INTO chat_blacklist (chat_id, user_id, reason, added_by)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(chat_id, user_id) DO UPDATE SET
               reason = excluded.reason,
               added_by = excluded.added_by,
               added_at = CURRENT_TIMESTAMP""",
        (chat_id, user_id, reason, added_by),
    )


async def remove_from_chat_blacklist(
    db: aiosqlite.Connection,
    chat_id: int,
    user_id: int,
) -> bool:
    """Returns True if a row was deleted."""
    async with db.execute(
        "DELETE FROM chat_blacklist WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id),
    ) as c:
        return c.rowcount > 0


async def is_in_chat_blacklist(
    db: aiosqlite.Connection,
    chat_id: int,
    user_id: int,
) -> bool:
    async with db.execute(
        "SELECT 1 FROM chat_blacklist WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id),
    ) as c:
        return (await c.fetchone()) is not None


async def get_chat_blacklist(
    db: aiosqlite.Connection,
    chat_id: int,
) -> list[dict]:
    async with db.execute(
        "SELECT user_id, reason, added_by, added_at FROM chat_blacklist WHERE chat_id = ? ORDER BY added_at DESC",
        (chat_id,),
    ) as c:
        rows = await c.fetchall()
    return [dict(r) for r in rows]


# ── Global blacklist ──────────────────────────────────────────────────────────

async def add_to_global_blacklist(
    db: aiosqlite.Connection,
    entity_type: str,
    entity_id: int,
    reason: Optional[str],
) -> None:
    await db.execute(
        """INSERT INTO global_blacklist (entity_type, entity_id, reason)
           VALUES (?, ?, ?)
           ON CONFLICT(entity_type, entity_id) DO UPDATE SET
               reason = excluded.reason,
               added_at = CURRENT_TIMESTAMP""",
        (entity_type, entity_id, reason),
    )


async def remove_from_global_blacklist(
    db: aiosqlite.Connection,
    entity_type: str,
    entity_id: int,
) -> bool:
    async with db.execute(
        "DELETE FROM global_blacklist WHERE entity_type = ? AND entity_id = ?",
        (entity_type, entity_id),
    ) as c:
        return c.rowcount > 0


async def is_globally_blocked(
    db: aiosqlite.Connection,
    entity_type: str,
    entity_id: int,
) -> bool:
    async with db.execute(
        "SELECT 1 FROM global_blacklist WHERE entity_type = ? AND entity_id = ?",
        (entity_type, entity_id),
    ) as c:
        return (await c.fetchone()) is not None


async def get_global_blacklist(
    db: aiosqlite.Connection,
) -> list[dict]:
    async with db.execute(
        "SELECT entity_type, entity_id, reason, added_at FROM global_blacklist ORDER BY added_at DESC",
    ) as c:
        rows = await c.fetchall()
    return [dict(r) for r in rows]
