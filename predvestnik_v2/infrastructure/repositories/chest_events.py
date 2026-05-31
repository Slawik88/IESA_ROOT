import aiosqlite
from datetime import datetime


async def get_active_chest(db: aiosqlite.Connection, chat_id: int) -> dict | None:
    async with db.execute(
        "SELECT * FROM chest_events WHERE chat_id = ? AND status = 'active' LIMIT 1",
        (chat_id,),
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def create_chest(db: aiosqlite.Connection, chat_id: int, expires_at: str) -> int:
    cursor = await db.execute(
        "INSERT INTO chest_events (chat_id, expires_at) VALUES (?, ?)",
        (chat_id, expires_at),
    )
    return cursor.lastrowid


async def close_chest(db: aiosqlite.Connection, chest_id: int) -> None:
    await db.execute("UPDATE chest_events SET status = 'closed' WHERE id = ?", (chest_id,))


async def claim_chest(
    db: aiosqlite.Connection,
    chest_id: int,
    user_id: int,
) -> int | None:
    """Atomically claim a chest spot. Returns the position (1-15) or None if already claimed / full."""
    async with db.execute(
        "SELECT COUNT(*) FROM chest_claims WHERE chest_id = ?", (chest_id,)
    ) as c:
        count = (await c.fetchone())[0]

    if count >= 15:
        return None

    try:
        position = count + 1
        await db.execute(
            "INSERT INTO chest_claims (chest_id, user_id, position) VALUES (?, ?, ?)",
            (chest_id, user_id, position),
        )
        return position
    except Exception:
        return None  # UNIQUE violation = already claimed


async def get_claims(db: aiosqlite.Connection, chest_id: int) -> list[dict]:
    async with db.execute(
        "SELECT user_id, position FROM chest_claims WHERE chest_id = ? ORDER BY position",
        (chest_id,),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_expired_active(db: aiosqlite.Connection) -> list[dict]:
    """Return active chests that have passed their expires_at."""
    async with db.execute(
        "SELECT * FROM chest_events WHERE status = 'active' AND expires_at <= datetime('now')"
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_qualifying_chats(db: aiosqlite.Connection, min_users: int) -> list[int]:
    """Chats with enough active users in the last 24h that don't currently have an active chest."""
    async with db.execute(
        """SELECT DISTINCT s.chat_tg_id
           FROM user_chat_stats s
           JOIN (
               SELECT chat_tg_id, COUNT(*) AS cnt
               FROM user_chat_stats
               WHERE last_message_at >= datetime('now', '-1 day')
               GROUP BY chat_tg_id
           ) active_counts ON active_counts.chat_tg_id = s.chat_tg_id
           LEFT JOIN chat_settings cs ON cs.chat_id = s.chat_tg_id
           WHERE active_counts.cnt >= ?
             AND COALESCE(cs.is_purging, 0) = 0
             AND NOT EXISTS (
                 SELECT 1 FROM chest_events ce
                 WHERE ce.chat_id = s.chat_tg_id AND ce.status = 'active'
             )
             AND (cs.last_chest_at IS NULL
                  OR cs.last_chest_at <= datetime('now', ?))""",
        (min_users, f"-{4} hours"),  # minimum 4 hours between chests
    ) as c:
        return [r[0] for r in await c.fetchall()]


async def update_last_chest_at(db: aiosqlite.Connection, chat_id: int) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await db.execute(
        "UPDATE chat_settings SET last_chest_at = ? WHERE chat_id = ?", (now, chat_id)
    )
