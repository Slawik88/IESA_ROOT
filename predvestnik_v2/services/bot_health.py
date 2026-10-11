"""Вкладка «Состояние» админки: жив ли бот, база, ошибки, чаты без прав, очереди.

Ошибки читаются из кольцевого буфера loguru в памяти процесса (с последнего перезапуска): отдельной таблицы нет.
Telegram спрашивается одним лёгким запросом getMe, ответ держится минуту.
"""
from __future__ import annotations

import os
import platform
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from loguru import logger

STARTED_AT = time.time()
_errors: deque[tuple[float, str]] = deque(maxlen=200)
_installed = False
_me_cache: tuple[float, dict] | None = None
ME_TTL = 60.0


def install() -> None:
    """Подписаться на ошибки loguru (один раз за процесс)."""
    global _installed
    if _installed:
        return
    _installed = True
    logger.add(lambda m: _errors.append((time.time(), str(m.record["message"])[:300])), level="ERROR", format="{message}")


def recent_errors(hours: int = 24, limit: int = 10) -> tuple[int, list[dict]]:
    since = time.time() - hours * 3600
    items = [(t, text) for t, text in _errors if t >= since]
    shown = [{"at": datetime.fromtimestamp(t, timezone.utc).isoformat(), "text": text} for t, text in reversed(items[-limit:])]
    return len(items), shown


def commit_sha() -> str:
    for key in ("DIGITALOCEAN_GIT_COMMIT_SHA", "SOURCE_COMMIT", "GIT_COMMIT", "COMMIT_SHA"):
        value = os.getenv(key, "").strip()
        if value:
            return value[:7]
    return ""


async def _one(db, sql: str, args: tuple = ()):
    async with db.execute(sql, args) as cur:
        return await cur.fetchone()


async def telegram_me(bot) -> dict:
    """getMe: доходит ли бот до Telegram и как зовётся. Не дольше 5 секунд, ответ кешируется."""
    global _me_cache
    if _me_cache and time.time() - _me_cache[0] < ME_TTL:
        return _me_cache[1]
    import asyncio
    started = time.perf_counter()
    try:
        me = await asyncio.wait_for(bot.me(), 5)
        info = {"ok": True, "username": me.username, "ms": round((time.perf_counter() - started) * 1000)}
    except Exception as exc:
        info = {"ok": False, "error": str(exc)[:160], "ms": round((time.perf_counter() - started) * 1000)}
    _me_cache = (time.time(), info)
    return info


async def counters(db) -> dict:
    """Чаты и игроки: где бот без прав, сколько удалили из чатов, сколько заблокировали бота."""
    from bot.chat.tracking import local_now
    quiet_since = (local_now().date() - timedelta(days=29)).isoformat()
    row = await _one(
        db, "SELECT COUNT(*) FILTER (WHERE bot_left_at IS NULL), COUNT(*) FILTER (WHERE bot_left_at IS NOT NULL), "
            "COUNT(*) FILTER (WHERE bot_left_at IS NULL AND bot_can_moderate = FALSE), "
            "COUNT(*) FILTER (WHERE bot_left_at IS NULL AND NOT EXISTS (SELECT 1 FROM daily_user_stats d "
            "WHERE d.chat_id = chat_settings.chat_id AND d.date >= ?)) FROM chat_settings WHERE chat_id < 0",
        (quiet_since,))
    chats = {"active": int(row[0]), "left": int(row[1]), "no_rights": int(row[2]), "quiet": int(row[3])}
    row = await _one(db, "SELECT COUNT(*), COUNT(*) FILTER (WHERE dm_blocked_at IS NOT NULL) FROM users WHERE user_tg_id > 0")
    players = {"total": int(row[0]), "blocked_bot": int(row[1])}
    return {"chats": chats, "players": players}


async def snapshot(db, bot=None) -> dict:
    started = time.perf_counter()
    await _one(db, "SELECT 1")
    db_ms = round((time.perf_counter() - started) * 1000, 1)
    pool = {}
    try:
        from infrastructure.database import get_pool
        p = get_pool()
        pool = {"size": p.get_size(), "idle": p.get_idle_size(), "max": p.get_max_size()}
    except Exception:
        pass
    count, recent = recent_errors()
    try:
        queues = {
            "broadcasts_running": int((await _one(db, "SELECT COUNT(*) FROM bot_broadcasts WHERE status = 'running'"))[0]),
            "broadcasts_scheduled": int((await _one(db, "SELECT COUNT(*) FROM bot_broadcasts WHERE status = 'scheduled'"))[0]),
            "reports_open": int((await _one(db, "SELECT COUNT(*) FROM bot_reports WHERE status IN ('new', 'in_work')"))[0]),
        }
    except Exception:   # таблиц рассылок или жалоб ещё нет
        queues = {"broadcasts_running": 0, "broadcasts_scheduled": 0, "reports_open": 0}
    return {
        "process": {"started_at": datetime.fromtimestamp(STARTED_AT, timezone.utc).isoformat(),
                    "uptime_seconds": int(time.time() - STARTED_AT), "python": platform.python_version(), "commit": commit_sha()},
        "database": {"ms": db_ms, "pool": pool},
        "telegram": await telegram_me(bot) if bot is not None else None,
        "errors": {"count_24h": count, "recent": recent},
        "queues": queues,
        **await counters(db),
    }
