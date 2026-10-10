"""Глобальная модерация: бан во всех чатах бота и «бот не отвечает игроку».

Глобальный бан — строка chat_blacklist с chat_id = 0: при входе в любой чат бот сразу
выгоняет игрока (как и при бане в одном чате), а при наложении — банит во всех известных чатах.
Блокировка — таблица bot_user_blocks: бот молча игнорирует команды игрока во всех чатах и в личке,
сообщения при этом считаются как обычно.
"""
from __future__ import annotations

import time

from loguru import logger

GLOBAL_CHAT = 0
TTL = 15.0

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS bot_user_blocks (
        user_id    BIGINT PRIMARY KEY,
        reason     TEXT   NOT NULL DEFAULT '',
        until      TIMESTAMPTZ,
        blocked_by BIGINT,
        blocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
)

_blocked: set[int] = set()
_loaded_at = -1e9


async def ensure_schema(db) -> None:
    for sql in STATEMENTS:
        await db.execute(sql)


def invalidate() -> None:
    global _loaded_at
    _loaded_at = -1e9


async def is_blocked(db, user_id: int) -> bool:
    global _blocked, _loaded_at
    if time.monotonic() - _loaded_at > TTL:
        async with db.execute("SELECT to_regclass('bot_user_blocks') IS NOT NULL") as cur:
            exists = (await cur.fetchone())[0]
        if exists:
            async with db.execute(
                "SELECT user_id FROM bot_user_blocks WHERE until IS NULL OR until > NOW()") as cur:
                _blocked = {int(r[0]) for r in await cur.fetchall()}
        else:
            _blocked = set()
        _loaded_at = time.monotonic()
    return int(user_id) in _blocked


async def block(db, user_id: int, actor_id: int, reason: str = "", days: int = 0) -> None:
    await db.execute(
        "INSERT INTO bot_user_blocks (user_id, reason, until, blocked_by) "
        "VALUES (?, ?, CASE WHEN ? > 0 THEN NOW() + make_interval(days => ?) END, ?) "
        "ON CONFLICT (user_id) DO UPDATE SET reason = EXCLUDED.reason, until = EXCLUDED.until, "
        "blocked_by = EXCLUDED.blocked_by, blocked_at = NOW()",
        (user_id, reason[:200], days, days, actor_id))
    invalidate()


async def unblock(db, user_id: int) -> None:
    await db.execute("DELETE FROM bot_user_blocks WHERE user_id = ?", (user_id,))
    invalidate()


async def block_info(db, user_id: int) -> dict | None:
    async with db.execute(
        "SELECT reason, until, blocked_by, blocked_at FROM bot_user_blocks "
        "WHERE user_id = ? AND (until IS NULL OR until > NOW())", (user_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    return {"reason": row[0] or "", "until": row[1].isoformat() if row[1] else None, "by": row[2],
            "at": row[3].isoformat() if row[3] else None}


async def ban_info(db, user_id: int) -> dict | None:
    async with db.execute(
        "SELECT reason, added_by, added_at FROM chat_blacklist WHERE chat_id = ? AND user_id = ?",
        (GLOBAL_CHAT, user_id)) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    return {"reason": row[0] or "", "by": row[1], "at": row[2].isoformat() if row[2] else None}


async def _known_chats(db) -> list[int]:
    async with db.execute("SELECT chat_id FROM chat_settings WHERE chat_id < 0 ORDER BY chat_id") as cur:
        return [int(r[0]) for r in await cur.fetchall()]


async def global_ban(bot, db, user_id: int, actor_id: int, reason: str = "") -> tuple[int, int]:
    """Бан навсегда во всех чатах. Возвращает (сколько чатов забанил, сколько не вышло)."""
    await db.execute(
        "INSERT INTO chat_blacklist (chat_id, user_id, reason, added_by, expires_at) VALUES (?, ?, ?, ?, NULL) "
        "ON CONFLICT (chat_id, user_id) DO UPDATE SET reason = EXCLUDED.reason, added_by = EXCLUDED.added_by, "
        "added_at = NOW(), expires_at = NULL",
        (GLOBAL_CHAT, user_id, reason or None, actor_id))
    done = failed = 0
    for chat_id in await _known_chats(db):
        try:
            await bot.ban_chat_member(chat_id, user_id)
            done += 1
            # Запоминаем, где бан поставил именно глобальный бан: снимать будем только там.
            await db.execute(
                "INSERT INTO moderation_logs (chat_id, user_id, admin_id, action) VALUES (?, ?, ?, 'global_ban_chat')",
                (chat_id, user_id, actor_id))
        except Exception as exc:   # бота могли выгнать из чата или лишить прав
            logger.debug(f"global ban {user_id} in {chat_id}: {exc}")
            failed += 1
    await db.execute("UPDATE user_chat_stats SET is_left = TRUE WHERE user_tg_id = ?", (user_id,))
    await db.execute(
        "INSERT INTO moderation_logs (chat_id, user_id, admin_id, action, reason) VALUES (?, ?, ?, 'global_ban', ?)",
        (GLOBAL_CHAT, user_id, actor_id, reason or None))
    return done, failed


async def global_unban(bot, db, user_id: int, actor_id: int) -> tuple[int, int]:
    """Снять глобальный бан только в тех чатах, где его поставил глобальный бан.

    Баны отдельных чатов — из бота (chat_blacklist) или руками в Telegram — остаются.
    """
    async with db.execute(
        "SELECT added_at FROM chat_blacklist WHERE chat_id = ? AND user_id = ?", (GLOBAL_CHAT, user_id)) as cur:
        row = await cur.fetchone()
    since = row[0] if row else None
    await db.execute("DELETE FROM chat_blacklist WHERE chat_id = ? AND user_id = ?", (GLOBAL_CHAT, user_id))
    async with db.execute(
        "SELECT DISTINCT chat_id FROM moderation_logs WHERE user_id = ? AND action = 'global_ban_chat' "
        "AND (?::timestamp IS NULL OR created_at >= ?::timestamp - INTERVAL '1 minute')", (user_id, since, since)) as cur:
        banned_here = {int(r[0]) for r in await cur.fetchall()}
    async with db.execute(
        "SELECT chat_id FROM chat_blacklist WHERE user_id = ? AND chat_id <> ? "
        "AND (expires_at IS NULL OR expires_at > NOW())", (user_id, GLOBAL_CHAT)) as cur:
        keep = {int(r[0]) for r in await cur.fetchall()}
    done = failed = 0
    for chat_id in sorted(banned_here - keep):
        try:
            await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
            done += 1
        except Exception as exc:
            logger.debug(f"global unban {user_id} in {chat_id}: {exc}")
            failed += 1
    await db.execute(
        "INSERT INTO moderation_logs (chat_id, user_id, admin_id, action) VALUES (?, ?, ?, 'global_unban')",
        (GLOBAL_CHAT, user_id, actor_id))
    return done, failed
