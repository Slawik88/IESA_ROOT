# infrastructure/repositories/chat.py
# timezone_offset is passed explicitly so this module has zero platform dependencies.
import aiosqlite


async def increment_stats_and_get_xp(
    db: aiosqlite.Connection,
    user_id: int,
    chat_id: int,
    timezone_offset: str = "+3 hours",
) -> dict:
    tz = timezone_offset
    query = """
        INSERT INTO user_chat_stats (
            user_tg_id, chat_tg_id,
            user_messages_count_per_day, user_messages_count_per_week,
            user_messages_count_per_month, user_messages_count_all_time,
            user_xp, last_message_at
        )
        VALUES (?, ?, 1, 1, 1, 1, 10, CURRENT_TIMESTAMP)
        ON CONFLICT(user_tg_id, chat_tg_id)
        DO UPDATE SET
            user_messages_count_per_last_day  = CASE WHEN strftime('%Y-%m-%d', last_message_at, ?) != strftime('%Y-%m-%d', 'now', ?) THEN user_messages_count_per_day  ELSE user_messages_count_per_last_day  END,
            user_messages_count_per_day       = CASE WHEN strftime('%Y-%m-%d', last_message_at, ?) != strftime('%Y-%m-%d', 'now', ?) THEN 1 ELSE user_messages_count_per_day  + 1 END,

            user_messages_count_per_last_week = CASE WHEN strftime('%W', last_message_at, ?) != strftime('%W', 'now', ?) THEN user_messages_count_per_week ELSE user_messages_count_per_last_week END,
            user_messages_count_per_week      = CASE WHEN strftime('%W', last_message_at, ?) != strftime('%W', 'now', ?) THEN 1 ELSE user_messages_count_per_week + 1 END,

            user_messages_count_per_last_month = CASE WHEN strftime('%m', last_message_at, ?) != strftime('%m', 'now', ?) THEN user_messages_count_per_month ELSE user_messages_count_per_last_month END,
            user_messages_count_per_month      = CASE WHEN strftime('%m', last_message_at, ?) != strftime('%m', 'now', ?) THEN 1 ELSE user_messages_count_per_month + 1 END,

            user_messages_count_all_time = user_messages_count_all_time + 1,
            user_xp          = user_xp + 10,
            last_message_at  = CURRENT_TIMESTAMP
        RETURNING user_xp, user_level
    """
    params = (user_id, chat_id, tz, tz, tz, tz, tz, tz, tz, tz, tz, tz, tz, tz)
    async with db.execute(query, params) as cursor:
        row = await cursor.fetchone()
        await db.commit()
        return dict(row)


async def update_level(db: aiosqlite.Connection, user_id: int, chat_id: int, new_level: int):
    await db.execute(
        "UPDATE user_chat_stats SET user_level = ? WHERE user_tg_id = ? AND chat_tg_id = ?",
        (new_level, user_id, chat_id),
    )
    await db.commit()


async def get_chat_stats(db: aiosqlite.Connection, user_id: int, chat_id: int) -> dict:
    async with db.execute(
        "SELECT * FROM user_chat_stats WHERE user_tg_id = ? AND chat_tg_id = ?",
        (user_id, chat_id),
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            return {"user_level": 1, "user_xp": 0, "user_messages_count_all_time": 0}
        return dict(row)


async def set_local_rank(db: aiosqlite.Connection, user_id: int, chat_id: int, rank_id: int):
    await db.execute(
        "UPDATE user_chat_stats SET local_rank = ? WHERE user_tg_id = ? AND chat_tg_id = ?",
        (rank_id, user_id, chat_id),
    )
    await db.commit()


async def get_local_rank(db: aiosqlite.Connection, user_id: int, chat_id: int) -> int:
    async with db.execute(
        "SELECT local_rank FROM user_chat_stats WHERE user_tg_id = ? AND chat_tg_id = ?",
        (user_id, chat_id),
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0

async def add_xp(db: aiosqlite.Connection, user_id: int, chat_id: int, amount: int) -> None:
    await db.execute(
        "UPDATE user_chat_stats SET user_xp = user_xp + ? WHERE user_tg_id = ? AND chat_tg_id = ?",
        (amount, user_id, chat_id),
    )
    await db.commit()


async def set_xp_lvl(db: aiosqlite.Connection, user_id: int, chat_id: int, xp: int, lvl: int):
    await db.execute(
        "UPDATE user_chat_stats SET user_xp = ?, user_level = ? WHERE user_tg_id = ? AND chat_tg_id = ?",
        (xp, lvl, user_id, chat_id)
    )
    await db.commit()


async def get_chat_admins(db: aiosqlite.Connection, chat_id: int) -> list[dict]:
    async with db.execute(
        """SELECT s.user_tg_id, s.local_rank, u.user_tg_username
        FROM user_chat_stats s
        LEFT JOIN users u ON s.user_tg_id = u.user_tg_id
        WHERE s.chat_tg_id = ? AND s.local_rank >= 1 AND s.is_left = 0
        ORDER BY s.local_rank DESC""",
        (chat_id,),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def get_chat_member_count(db: aiosqlite.Connection, chat_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM user_chat_stats WHERE chat_tg_id = ? AND local_rank = 0 AND is_left = 0",
        (chat_id,),
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0