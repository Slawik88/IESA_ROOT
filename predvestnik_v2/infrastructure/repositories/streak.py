import aiosqlite
from datetime import datetime, timedelta
from typing import Optional

# Стрик ЕДИНЫЙ на все чаты: храним в одной строке daily_login с sentinel chat_id = 0.
# Любое сообщение в любом чате обновляет именно её (один стрик, одна награда в день).
GLOBAL_STREAK_CHAT_ID = 0


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
    db,
    user_id: int,
    chat_id: int,
    streak: int,
    today: datetime,
    recovery_streak: int = 0,
    recovery_missed_days: int = 0,
    recovery_expires=None,
) -> bool:
    """Atomically claim the daily notification. Returns True only on first call for this day."""
    async with db.execute(
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
               recovery_expires = excluded.recovery_expires
           WHERE daily_login.last_notified IS NULL
              OR daily_login.last_notified::date < excluded.last_notified::date
           RETURNING last_notified""",
        (user_id, chat_id, streak, today, today,
         recovery_streak, recovery_missed_days, recovery_expires),
    ) as c:
        row = await c.fetchone()
    return row is not None


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


# ── Глобальный стрик (один на все чаты, sentinel chat_id = 0) ────────────────────
async def get_global_streak(db, user_id: int) -> dict:
    return await get_streak(db, user_id, GLOBAL_STREAK_CHAT_ID)


async def upsert_global_streak(
    db, user_id: int, streak: int, today: datetime,
    recovery_streak: int = 0, recovery_missed_days: int = 0, recovery_expires=None,
) -> bool:
    return await upsert_streak(
        db, user_id, GLOBAL_STREAK_CHAT_ID, streak, today,
        recovery_streak, recovery_missed_days, recovery_expires,
    )


async def update_global_streak_after_recovery(db, user_id: int, restored_streak: int) -> None:
    await update_streak_after_recovery(db, user_id, GLOBAL_STREAK_CHAT_ID, restored_streak)


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
