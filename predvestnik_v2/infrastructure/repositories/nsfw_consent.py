import aiosqlite


async def get_consent(db: aiosqlite.Connection, target_id: int, chat_id: int) -> str | None:
    """Return 'allowed', 'denied', or None (never asked)."""
    async with db.execute(
        "SELECT status FROM user_nsfw_consents WHERE target_user_id = ? AND chat_id = ?",
        (target_id, chat_id),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else None


async def set_consent(
    db: aiosqlite.Connection,
    target_id: int,
    chat_id: int,
    status: str,
) -> None:
    await db.execute(
        "INSERT INTO user_nsfw_consents (target_user_id, chat_id, status) VALUES (?, ?, ?) "
        "ON CONFLICT(target_user_id, chat_id) DO UPDATE SET status = excluded.status, "
        "set_at = CURRENT_TIMESTAMP",
        (target_id, chat_id, status),
    )
    await db.commit()
