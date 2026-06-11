# infrastructure/repositories/stats.py
import aiosqlite

# all_time still reads from the counter column; period-based reads from daily_user_stats
# so that stale lazy-reset counters can't show players who haven't written today.


async def get_top_messages(
    db: aiosqlite.Connection, chat_id: int, period: str, limit: int = 500
) -> list[dict]:
    """all_time top — reads from the cumulative counter column."""
    async with db.execute(
        "SELECT s.user_tg_id, u.user_tg_username, "
        "s.user_messages_count_all_time AS msg_count, "
        "(v.user_id IS NOT NULL) AS is_vip "
        "FROM user_chat_stats s "
        "LEFT JOIN users u ON s.user_tg_id = u.user_tg_id "
        "LEFT JOIN vip_subscriptions v ON v.user_id = s.user_tg_id AND v.expires_at > NOW() "
        "WHERE s.chat_tg_id = ? AND s.is_left = FALSE "
        "AND s.user_messages_count_all_time > 0 "
        "ORDER BY s.user_messages_count_all_time DESC LIMIT ?",
        (chat_id, limit),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def get_top_messages_for_dates(
    db: aiosqlite.Connection,
    chat_id: int,
    date_start: str,
    date_end: str,
    limit: int = 500,
) -> list[dict]:
    """Period-based top using daily_user_stats — accurate even for inactive days."""
    async with db.execute(
        "SELECT d.user_id AS user_tg_id, u.user_tg_username, "
        "SUM(d.message_count) AS msg_count, "
        "(v.user_id IS NOT NULL) AS is_vip "
        "FROM daily_user_stats d "
        "LEFT JOIN users u ON d.user_id = u.user_tg_id "
        "LEFT JOIN user_chat_stats s "
        "  ON s.user_tg_id = d.user_id AND s.chat_tg_id = d.chat_id "
        "LEFT JOIN vip_subscriptions v ON v.user_id = d.user_id AND v.expires_at > NOW() "
        "WHERE d.chat_id = ? AND d.date >= ? AND d.date <= ? "
        "AND NOT (s.is_left = TRUE) "
        "GROUP BY d.user_id, u.user_tg_username, v.user_id "
        "HAVING SUM(d.message_count) > 0 "
        "ORDER BY msg_count DESC LIMIT ?",
        (chat_id, date_start, date_end, limit),
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
    # PostgreSQL requires all non-aggregated columns in GROUP BY.
    async with db.execute(
        "SELECT s.user_tg_id, u.user_tg_username, "
        "SUM(s.user_messages_count_all_time) AS value, "
        "(v.user_id IS NOT NULL) AS is_vip "
        "FROM user_chat_stats s LEFT JOIN users u ON s.user_tg_id = u.user_tg_id "
        "LEFT JOIN vip_subscriptions v ON v.user_id = s.user_tg_id AND v.expires_at > NOW() "
        f"GROUP BY s.user_tg_id, u.user_tg_username, v.user_id "
        f"HAVING SUM(s.user_messages_count_all_time) >= {_MIN_GLOBAL_MSGS} "
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
