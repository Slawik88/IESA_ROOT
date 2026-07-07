# infrastructure/repositories/moderation.py
import aiosqlite


async def set_user_left_status(
    db: aiosqlite.Connection, chat_id: int, user_id: int, is_left: bool
):
    await db.execute(
        "UPDATE user_chat_stats SET is_left = ? WHERE user_tg_id = ? AND chat_tg_id = ?",
        (is_left, user_id, chat_id),
    )
    await db.commit()


async def log_moderation_action(
    db: aiosqlite.Connection, chat_id: int, user_id: int, admin_id: int, action: str,
    reason: str | None = None,
):
    await db.execute(
        "INSERT INTO moderation_logs (chat_id, user_id, admin_id, action, reason) VALUES (?, ?, ?, ?, ?)",
        (chat_id, user_id, admin_id, action, reason),
    )
    await db.commit()


async def remove_ban_log(db: aiosqlite.Connection, chat_id: int, user_id: int):
    await db.execute(
        "DELETE FROM moderation_logs WHERE chat_id = ? AND user_id = ? AND action = 'ban'",
        (chat_id, user_id),
    )
    await db.commit()


async def get_moderation_list(
    db: aiosqlite.Connection, chat_id: int, action: str
) -> list[dict]:
    async with db.execute(
        "SELECT m.user_id, u.user_tg_username FROM moderation_logs m "
        "LEFT JOIN users u ON m.user_id = u.user_tg_id "
        "WHERE m.chat_id = ? AND m.action = ? ORDER BY m.created_at DESC",
        (chat_id, action),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def get_left_users(db: aiosqlite.Connection, chat_id: int) -> list[dict]:
    async with db.execute(
        "SELECT s.user_tg_id, u.user_tg_username FROM user_chat_stats s "
        "LEFT JOIN users u ON s.user_tg_id = u.user_tg_id "
        "WHERE s.chat_tg_id = ? AND s.is_left = TRUE",
        (chat_id,),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def get_chat_settings(db: aiosqlite.Connection, chat_id: int) -> dict:
    async with db.execute(
        "SELECT shield_duration_days, max_warnings, is_purging, purge_min_rank, "
        "COALESCE(purge_action_rank, 2) AS purge_action_rank, "
        "COALESCE(rank_chat_lock, 4) AS rank_chat_lock, "
        "COALESCE(rank_warn, 2) AS rank_warn, "
        "COALESCE(rank_mute, 1) AS rank_mute, "
        "COALESCE(rank_kick, 1) AS rank_kick, "
        "COALESCE(rank_ban, 2) AS rank_ban, "
        "COALESCE(rank_shield, 4) AS rank_shield, "
        "COALESCE(rank_immune, 5) AS rank_immune, "
        "COALESCE(events_enabled, 1) AS events_enabled, "
        "COALESCE(nsfw_warps_allowed, 1) AS nsfw_warps_allowed, "
        "COALESCE(auction_min_rank, 0) AS auction_min_rank, "
        "COALESCE(rank_duel, 0) AS rank_duel, "
        "COALESCE(rank_marriage, 0) AS rank_marriage, "
        "COALESCE(rank_give, 0) AS rank_give, "
        "COALESCE(module_shop, 1) AS module_shop, "
        "COALESCE(module_gacha, 1) AS module_gacha, "
        "COALESCE(module_expeditions, 1) AS module_expeditions, "
        "COALESCE(module_auction, 1) AS module_auction, "
        "COALESCE(module_games, 1) AS module_games, "
        "COALESCE(module_exchange, 1) AS module_exchange, "
        "COALESCE(module_quests, 1) AS module_quests, "
        "COALESCE(module_zoo, 1) AS module_zoo, "
        "COALESCE(module_warps, 1) AS module_warps, "
        "COALESCE(module_daily_deal, 1) AS module_daily_deal "
        "FROM chat_settings WHERE chat_id = ?",
        (chat_id,),
    ) as cursor:
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return {
            "shield_duration_days": 0, "max_warnings": 3, "is_purging": 0, "purge_min_rank": 4,
            "purge_action_rank": 2, "rank_chat_lock": 4,
            "rank_warn": 2, "rank_mute": 1, "rank_kick": 1, "rank_ban": 2,
            "rank_shield": 4, "rank_immune": 5,
            "events_enabled": 1, "nsfw_warps_allowed": 1, "auction_min_rank": 0,
            "rank_duel": 0, "rank_marriage": 0, "rank_give": 0,
            "module_shop": 1, "module_gacha": 1, "module_expeditions": 1,
            "module_auction": 1, "module_games": 1, "module_exchange": 1,
            "module_quests": 1, "module_zoo": 1, "module_warps": 1, "module_daily_deal": 1,
        }


async def update_chat_settings(db: aiosqlite.Connection, chat_id: int, **kwargs):
    if not kwargs:
        return
    # Ensure row exists so UPDATE below isn't silently a no-op for new chats
    await db.execute(
        "INSERT INTO chat_settings (chat_id) VALUES (?) ON CONFLICT (chat_id) DO NOTHING",
        (chat_id,),
    )
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    await db.execute(
        f"UPDATE chat_settings SET {set_clause} WHERE chat_id = ?",
        [*kwargs.values(), chat_id],
    )
    await db.commit()


async def set_immunity(
    db: aiosqlite.Connection,
    chat_id: int,
    user_id: int,
    is_immune: int,
    immune_until: str | None = None,
):
    await _ensure_chat_stats_row(db, chat_id, user_id)
    await db.execute(
        "UPDATE user_chat_stats SET is_immune = ?, immune_until = ? "
        "WHERE user_tg_id = ? AND chat_tg_id = ?",
        (bool(is_immune), immune_until, user_id, chat_id),
    )
    await db.commit()


async def _ensure_chat_stats_row(db: aiosqlite.Connection, chat_id: int, user_id: int) -> None:
    """Гарантирует, что для пары (user, chat) есть строка в user_chat_stats.
    Нужно для модерации над новичками, которые ещё не писали в чат."""
    await db.execute("INSERT OR IGNORE INTO users (user_tg_id) VALUES (?)", (user_id,))
    await db.execute(
        "INSERT OR IGNORE INTO user_chat_stats (user_tg_id, chat_tg_id) VALUES (?, ?)",
        (user_id, chat_id),
    )


async def add_warn(
    db: aiosqlite.Connection,
    chat_id: int,
    user_id: int,
    admin_id: int,
    reason: str | None,
) -> int:
    await _ensure_chat_stats_row(db, chat_id, user_id)
    await db.execute(
        "UPDATE user_chat_stats SET warnings = warnings + 1 WHERE user_tg_id = ? AND chat_tg_id = ?",
        (user_id, chat_id),
    )
    await db.execute(
        "INSERT INTO user_warnings (chat_id, user_id, admin_id, reason) VALUES (?, ?, ?, ?)",
        (chat_id, user_id, admin_id, reason),
    )
    await db.commit()
    async with db.execute(
        "SELECT warnings FROM user_chat_stats WHERE user_tg_id = ? AND chat_tg_id = ?",
        (user_id, chat_id),
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 1


async def remove_warn(db: aiosqlite.Connection, chat_id: int, user_id: int, count: int = 1) -> int:
    await _ensure_chat_stats_row(db, chat_id, user_id)
    await db.execute(
        "UPDATE user_chat_stats SET warnings = GREATEST(0, warnings - ?) "
        "WHERE user_tg_id = ? AND chat_tg_id = ?",
        (count, user_id, chat_id),
    )
    await db.commit()
    async with db.execute(
        "SELECT warnings FROM user_chat_stats WHERE user_tg_id = ? AND chat_tg_id = ?",
        (user_id, chat_id),
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def clear_warns(db: aiosqlite.Connection, chat_id: int, user_id: int):
    await db.execute(
        "UPDATE user_chat_stats SET warnings = 0 WHERE user_tg_id = ? AND chat_tg_id = ?",
        (user_id, chat_id),
    )
    await db.commit()
