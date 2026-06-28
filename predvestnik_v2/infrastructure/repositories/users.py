# infrastructure/repositories/users.py
import aiosqlite


async def update_user(db: aiosqlite.Connection, user_id: int, username: str | None):
    """Upsert: register user or refresh username if it changed.

    Block 10: новые игроки вставляются с onboarded=FALSE (колонка иначе DEFAULT
    TRUE — существующие игроки набор не получают). Флаг переключает только
    services.onboarding.grant_starter_kit.
    """
    await db.execute(
        "INSERT INTO users (user_tg_id, user_tg_username, onboarded) VALUES (?, ?, FALSE) "
        "ON CONFLICT(user_tg_id) DO UPDATE SET user_tg_username = ?",
        (user_id, username, username),
    )
    await db.commit()


async def get_user_id_by_username(db: aiosqlite.Connection, username: str) -> int | None:
    clean = username.lstrip("@")
    async with db.execute(
        "SELECT user_tg_id FROM users WHERE LOWER(user_tg_username) = LOWER(?)",
        (clean,),
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_user_name(db: aiosqlite.Connection, user_id: int) -> str:
    async with db.execute(
        "SELECT user_tg_username FROM users WHERE user_tg_id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row and row[0] else str(user_id)


async def create_user(db: aiosqlite.Connection, user_id: int, username: str | None):
    await db.execute(
        "INSERT OR IGNORE INTO users (user_tg_id, user_tg_username) VALUES (?, ?)",
        (user_id, username),
    )
    await db.commit()


async def set_global_rank(db: aiosqlite.Connection, user_id: int, rank_id: int):
    await db.execute(
        "UPDATE users SET global_rank = ? WHERE user_tg_id = ?", (rank_id, user_id)
    )
    await db.commit()


async def get_global_rank(db: aiosqlite.Connection, user_id: int) -> int:
    async with db.execute(
        "SELECT global_rank FROM users WHERE user_tg_id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def accept_tos(db: aiosqlite.Connection, user_id: int,
                     username: str | None = None) -> None:
    """БЛОК22: зафиксировать принятие документов. Idempotent — повторное принятие
    не перезаписывает время первого согласия. Создаёт строку при отсутствии."""
    await db.execute(
        "INSERT INTO users (user_tg_id, user_tg_username, tos_accepted_at) "
        "VALUES (?, ?, NOW()) "
        "ON CONFLICT(user_tg_id) DO UPDATE SET "
        "tos_accepted_at = COALESCE(users.tos_accepted_at, NOW())",
        (user_id, username),
    )
    await db.commit()


async def get_first_seen(db: aiosqlite.Connection, user_id: int) -> str | None:
    """Return ISO date string of the earliest joined_at across all chats, or None."""
    async with db.execute(
        "SELECT MIN(joined_at) FROM user_chat_stats WHERE user_tg_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()
    return row[0] if row and row[0] else None


async def get_messages_global(db: aiosqlite.Connection, user_id: int) -> dict:
    """Return sum of per-day, per-week, all-time messages across all chats."""
    async with db.execute(
        """SELECT
               COALESCE(SUM(user_messages_count_per_day), 0)   AS day,
               COALESCE(SUM(user_messages_count_per_week), 0)  AS week,
               COALESCE(SUM(user_messages_count_all_time), 0)  AS all_time
           FROM user_chat_stats WHERE user_tg_id = ?""",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    if not row:
        return {"day": 0, "week": 0, "all_time": 0}
    return {"day": row[0], "week": row[1], "all_time": row[2]}


async def get_nickname(db: aiosqlite.Connection, user_id: int, chat_id: int) -> str | None:
    async with db.execute(
        "SELECT nickname FROM user_nicknames WHERE user_id = ? AND chat_id = ?",
        (user_id, chat_id),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else None


async def set_nickname(
    db: aiosqlite.Connection, user_id: int, chat_id: int, nickname: str
) -> None:
    await db.execute(
        "INSERT INTO user_nicknames (user_id, chat_id, nickname) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, chat_id) DO UPDATE SET nickname = excluded.nickname, "
        "set_at = CURRENT_TIMESTAMP",
        (user_id, chat_id, nickname),
    )
    await db.commit()


async def delete_nickname(db: aiosqlite.Connection, user_id: int, chat_id: int) -> None:
    await db.execute(
        "DELETE FROM user_nicknames WHERE user_id = ? AND chat_id = ?",
        (user_id, chat_id),
    )
    await db.commit()
