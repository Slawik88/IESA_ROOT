import aiosqlite
from datetime import datetime, timedelta


async def get_streak(db: aiosqlite.Connection, user_id: int, chat_id: int) -> dict:
    async with db.execute(
        "SELECT streak, last_login, last_notified, recovery_streak, "
        "recovery_missed_days, recovery_expires "
        "FROM daily_login WHERE user_id = ? AND chat_id = ?",
        (user_id, chat_id),
    ) as c:
        row = await c.fetchone()
    if not row:
        return {
            "streak": 0,
            "last_login": None,
            "last_notified": None,
            "recovery_streak": 0,
            "recovery_missed_days": 0,
            "recovery_expires": None,
        }
    return dict(row)


async def upsert_streak(
    db: aiosqlite.Connection,
    user_id: int,
    chat_id: int,
    streak: int,
    today: str,
    recovery_streak: int = 0,
    recovery_missed_days: int = 0,
    recovery_expires: str = None,
) -> None:
    await db.execute(
        """INSERT INTO daily_login
            (user_id, chat_id, streak, last_login, last_notified,
             recovery_streak, recovery_missed_days, recovery_expires)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(user_id, chat_id) DO UPDATE SET
               streak = excluded.streak,
               last_login = excluded.last_login,
               last_notified = excluded.last_notified,
               recovery_streak = excluded.recovery_streak,
               recovery_missed_days = excluded.recovery_missed_days,
               recovery_expires = excluded.recovery_expires""",
        (user_id, chat_id, streak, today, today,
         recovery_streak, recovery_missed_days, recovery_expires),
    )


async def update_streak_after_recovery(
    db: aiosqlite.Connection,
    user_id: int,
    chat_id: int,
    restored_streak: int,
) -> None:
    await db.execute(
        """UPDATE daily_login SET
               streak = ?,
               recovery_streak = 0,
               recovery_missed_days = 0,
               recovery_expires = NULL
           WHERE user_id = ? AND chat_id = ?""",
        (restored_streak, user_id, chat_id),
    )


async def get_chat_timezone(db: aiosqlite.Connection, chat_id: int) -> int:
    """Return the chat's UTC offset integer (default 0)."""
    async with db.execute(
        "SELECT timezone_offset FROM chat_settings WHERE chat_id = ?", (chat_id,)
    ) as c:
        row = await c.fetchone()
    if not row or row[0] is None:
        return 0
    return int(row[0])


async def set_chat_timezone(db: aiosqlite.Connection, chat_id: int, offset: int) -> None:
    await db.execute(
        "UPDATE chat_settings SET timezone_offset = ? WHERE chat_id = ?",
        (offset, chat_id),
    )
    await db.commit()
