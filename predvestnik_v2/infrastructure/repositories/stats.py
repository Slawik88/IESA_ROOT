# infrastructure/repositories/stats.py
import aiosqlite

# Safe column whitelist — prevents SQL injection via dynamic column names.
_COLUMNS_MAP = {
    "day":       "user_messages_count_per_day",
    "week":      "user_messages_count_per_week",
    "all_time":  "user_messages_count_all_time",
    "last_day":  "user_messages_count_per_last_day",
    "last_week": "user_messages_count_per_last_week",
}


async def get_top_messages(
    db: aiosqlite.Connection, chat_id: int, period: str, limit: int = 500
) -> list[dict]:
    col = _COLUMNS_MAP.get(period, "user_messages_count_all_time")
    async with db.execute(
        f"SELECT s.user_tg_id, u.user_tg_username, s.{col} AS msg_count "
        f"FROM user_chat_stats s "
        f"LEFT JOIN users u ON s.user_tg_id = u.user_tg_id "
        f"WHERE s.chat_tg_id = ? AND s.is_left = FALSE AND s.{col} > 0 "
        f"ORDER BY s.{col} DESC LIMIT ?",
        (chat_id, limit),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def get_zero_message_users(
    db: aiosqlite.Connection, chat_id: int, period: str
) -> list[dict]:
    """Returns users in chat who have 0 messages in the given period."""
    col = _COLUMNS_MAP.get(period, "user_messages_count_all_time")
    async with db.execute(
        f"SELECT s.user_tg_id, u.user_tg_username "
        f"FROM user_chat_stats s "
        f"LEFT JOIN users u ON s.user_tg_id = u.user_tg_id "
        f"WHERE s.chat_tg_id = ? AND s.is_left = FALSE AND (s.{col} IS NULL OR s.{col} = 0) "
        f"ORDER BY u.user_tg_username NULLS LAST LIMIT 50",
        (chat_id,),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


# ── Extended tops (B17) ──────────────────────────────────────────────────────

_MIN_GLOBAL_MSGS = 100  # minimum all_time messages for global tops


async def _local_user_ids(db: aiosqlite.Connection, chat_id: int) -> list[int]:
    async with db.execute(
        "SELECT user_tg_id FROM user_chat_stats WHERE chat_tg_id = ? AND is_left = FALSE",
        (chat_id,),
    ) as c:
        return [r[0] for r in await c.fetchall()]


async def _global_user_ids(db: aiosqlite.Connection) -> list[int]:
    async with db.execute(
        "SELECT DISTINCT user_tg_id FROM user_chat_stats "
        f"WHERE user_messages_count_all_time >= {_MIN_GLOBAL_MSGS}"
    ) as c:
        return [r[0] for r in await c.fetchall()]


async def get_top_mora(db: aiosqlite.Connection, chat_id: int | None, limit: int = 10) -> list[dict]:
    ids = await _local_user_ids(db, chat_id) if chat_id else await _global_user_ids(db)
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    async with db.execute(
        f"SELECT u.user_tg_id, u.user_tg_username, u.user_balance_mora AS value "
        f"FROM users u WHERE u.user_tg_id IN ({placeholders}) "
        f"ORDER BY u.user_balance_mora DESC LIMIT ?",
        (*ids, limit),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_top_diamonds(db: aiosqlite.Connection, chat_id: int | None, limit: int = 10) -> list[dict]:
    ids = await _local_user_ids(db, chat_id) if chat_id else await _global_user_ids(db)
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    async with db.execute(
        f"SELECT u.user_tg_id, u.user_tg_username, u.user_balance_diamonds AS value "
        f"FROM users u WHERE u.user_tg_id IN ({placeholders}) "
        f"ORDER BY u.user_balance_diamonds DESC LIMIT ?",
        (*ids, limit),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_top_pet_levels(db: aiosqlite.Connection, chat_id: int | None, limit: int = 10) -> list[dict]:
    ids = await _local_user_ids(db, chat_id) if chat_id else await _global_user_ids(db)
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    async with db.execute(
        f"SELECT p.owner_id AS user_tg_id, u.user_tg_username, "
        f"MAX(COALESCE(p.pet_level, 1)) AS value "
        f"FROM pets p LEFT JOIN users u ON p.owner_id = u.user_tg_id "
        f"WHERE p.owner_id IN ({placeholders}) AND COALESCE(p.pet_level, 1) >= 2 "
        f"GROUP BY p.owner_id ORDER BY value DESC LIMIT ?",
        (*ids, limit),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_top_achievements(db: aiosqlite.Connection, chat_id: int | None, limit: int = 10) -> list[dict]:
    ids = await _local_user_ids(db, chat_id) if chat_id else await _global_user_ids(db)
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    async with db.execute(
        f"SELECT a.user_id AS user_tg_id, u.user_tg_username, "
        f"COUNT(*) AS value "
        f"FROM achievements a LEFT JOIN users u ON a.user_id = u.user_tg_id "
        f"WHERE a.user_id IN ({placeholders}) AND a.level > 0 "
        f"GROUP BY a.user_id ORDER BY value DESC LIMIT ?",
        (*ids, limit),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_top_messages_global(db: aiosqlite.Connection, limit: int = 10) -> list[dict]:
    async with db.execute(
        "SELECT s.user_tg_id, u.user_tg_username, "
        "SUM(s.user_messages_count_all_time) AS value "
        "FROM user_chat_stats s LEFT JOIN users u ON s.user_tg_id = u.user_tg_id "
        f"GROUP BY s.user_tg_id HAVING SUM(s.user_messages_count_all_time) >= {_MIN_GLOBAL_MSGS} "
        "ORDER BY value DESC LIMIT ?",
        (limit,),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_top_streaks(db: aiosqlite.Connection, chat_id: int | None, limit: int = 10) -> list[dict]:
    ids = await _local_user_ids(db, chat_id) if chat_id else await _global_user_ids(db)
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    async with db.execute(
        f"SELECT dl.user_id AS user_tg_id, u.user_tg_username, MAX(dl.streak) AS value "
        f"FROM daily_login dl LEFT JOIN users u ON dl.user_id = u.user_tg_id "
        f"WHERE dl.user_id IN ({placeholders}) "
        f"GROUP BY dl.user_id ORDER BY value DESC LIMIT ?",
        (*ids, limit),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_top_auction_sales(db: aiosqlite.Connection, chat_id: int | None, limit: int = 10) -> list[dict]:
    ids = await _local_user_ids(db, chat_id) if chat_id else await _global_user_ids(db)
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    async with db.execute(
        f"SELECT al.seller_id AS user_tg_id, u.user_tg_username, COUNT(*) AS value "
        f"FROM auction_lots al LEFT JOIN users u ON al.seller_id = u.user_tg_id "
        f"WHERE al.seller_id IN ({placeholders}) AND al.status = 'sold' "
        f"GROUP BY al.seller_id ORDER BY value DESC LIMIT ?",
        (*ids, limit),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_inactive_users(
    db: aiosqlite.Connection, chat_id: int, days_limit: int = 4
) -> list[dict]:
    async with db.execute(
        "SELECT s.user_tg_id, u.user_tg_username, s.last_message_at, "
        "EXTRACT(DAY FROM NOW() - s.last_message_at)::INTEGER AS days_offline "
        "FROM user_chat_stats s "
        "LEFT JOIN users u ON s.user_tg_id = u.user_tg_id "
        "WHERE s.chat_tg_id = ? AND s.is_left = FALSE "
        "AND EXTRACT(DAY FROM NOW() - s.last_message_at) >= ? "
        "ORDER BY days_offline DESC",
        (chat_id, days_limit),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]
