"""Доступ владельцев чатов к админке (ADM-02, этап 2).

Владелец — любой, кто создал группу с ботом, поэтому доступ закрыт по умолчанию:
- общий выключатель (по умолчанию выключен) и список отозванных людей, действуют сразу;
- владение подтверждается Telegram-ом (создатель группы из get_chat_administrators), а не записью в БД:
  сбой Telegram = отказ; `owner_override` и устаревший `owner_id` входа не дают; бот вышел из чата = доступа нет;
- результат проверки живёт TTL секунд, параллельные запросы по одному чату схлопываются в один вызов Telegram;
- чатов на человека — не больше MAX_CHATS.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque

from loguru import logger

TTL = 60.0         # сколько секунд верен ответ Telegram о владельце
FAIL_TTL = 10.0    # сбой не повторяем на каждый запрос
MAX_CHATS = 10     # чатов на одного человека
MAX_CALLS_PER_SEC = 15   # вызовов getChatAdministrators в секунду на весь сервер: больше — отказ, а не очередь
MAX_PARALLEL = 5         # одновременных вызовов Telegram

STATEMENTS = (
    "CREATE TABLE IF NOT EXISTS admin_owner_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, "
    "updated_by BIGINT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())",
    "CREATE TABLE IF NOT EXISTS admin_owner_blocked (user_id BIGINT PRIMARY KEY, reason TEXT NOT NULL DEFAULT '', "
    "added_by BIGINT NOT NULL, added_at TIMESTAMPTZ NOT NULL DEFAULT NOW())",
)
_ready = False
_cache: dict[tuple[int, int], tuple[float, bool]] = {}   # (чат, человек) -> (до какого момента верно, владелец ли)
_locks: dict[int, asyncio.Lock] = {}
_calls: deque[float] = deque()   # когда ходили в Telegram за последнюю секунду
_parallel: asyncio.Semaphore | None = None


async def _ensure(db) -> None:
    global _ready
    if not _ready:
        for sql in STATEMENTS:
            await db.execute(sql)
        _ready = True


def reset_cache() -> None:   # для тестов
    _cache.clear()
    _locks.clear()
    _calls.clear()


async def enabled(db) -> bool:
    await _ensure(db)
    async with db.execute("SELECT value FROM admin_owner_settings WHERE key = 'enabled'") as cur:
        row = await cur.fetchone()
    return bool(row and row[0] == "on")


async def set_enabled(db, actor_id: int, on: bool) -> None:
    await _ensure(db)
    await db.execute(
        "INSERT INTO admin_owner_settings (key, value, updated_by) VALUES ('enabled', ?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, updated_at = NOW()",
        ("on" if on else "off", actor_id))


async def is_blocked(db, user_id: int) -> bool:
    await _ensure(db)
    async with db.execute("SELECT 1 FROM admin_owner_blocked WHERE user_id = ?", (user_id,)) as cur:
        return await cur.fetchone() is not None


async def set_blocked(db, actor_id: int, user_id: int, blocked: bool, reason: str = "") -> None:
    await _ensure(db)
    if blocked:
        await db.execute(
            "INSERT INTO admin_owner_blocked (user_id, reason, added_by) VALUES (?, ?, ?) "
            "ON CONFLICT (user_id) DO UPDATE SET reason = EXCLUDED.reason, added_by = EXCLUDED.added_by, added_at = NOW()",
            (user_id, reason[:200], actor_id))
    else:
        await db.execute("DELETE FROM admin_owner_blocked WHERE user_id = ?", (user_id,))


async def blocked_list(db) -> list[dict]:
    await _ensure(db)
    async with db.execute("SELECT b.user_id, u.user_tg_username, b.reason, b.added_at FROM admin_owner_blocked b "
                          "LEFT JOIN users u ON u.user_tg_id = b.user_id ORDER BY b.added_at DESC LIMIT 200") as cur:
        return [{"id": int(r[0]), "username": r[1], "reason": r[2], "at": r[3].isoformat()} for r in await cur.fetchall()]


async def _ask_telegram(bot, chat_id: int, user_id: int) -> bool:
    """Создатель группы по данным Telegram. Любой сбой — «нет»."""
    global _parallel
    now = time.monotonic()
    while _calls and _calls[0] <= now - 1.0:
        _calls.popleft()
    if len(_calls) >= MAX_CALLS_PER_SEC:   # перегрузка: Telegram не трогаем, отвечаем отказом (закрыто по умолчанию)
        logger.warning("owner check skipped: too many Telegram calls per second")
        return False
    _calls.append(now)
    if _parallel is None:
        _parallel = asyncio.Semaphore(MAX_PARALLEL)
    try:
        async with _parallel:
            admins = await bot.get_chat_administrators(chat_id)
    except Exception as exc:   # noqa: BLE001
        logger.warning(f"owner check failed for {chat_id}: {exc}")
        return False
    return any(a.status == "creator" and int(a.user.id) == int(user_id) for a in admins)


async def is_telegram_owner(bot, chat_id: int, user_id: int, *, now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    hit = _cache.get((chat_id, user_id))
    if hit and hit[0] > now:
        return hit[1]
    lock = _locks.setdefault(chat_id, asyncio.Lock())
    async with lock:   # одновременные запросы по одному чату ждут один вызов Telegram
        now = time.monotonic() if now is None else now
        hit = _cache.get((chat_id, user_id))
        if hit and hit[0] > now:
            return hit[1]
        ok = await _ask_telegram(bot, chat_id, user_id)
        _cache[(chat_id, user_id)] = (time.monotonic() + (TTL if ok else FAIL_TTL), ok)
        return ok


async def verified_chats(db, bot, user_id: int) -> list[dict]:
    """Чаты, где человек сейчас создатель группы (по Telegram), бот в чате, и не больше MAX_CHATS."""
    async with db.execute(
        "SELECT chat_id, chat_title FROM chat_settings WHERE owner_id = ? AND bot_left_at IS NULL "
        "AND chat_id < 0 ORDER BY chat_id LIMIT ?", (user_id, MAX_CHATS)) as cur:
        candidates = [(int(r[0]), r[1]) for r in await cur.fetchall()]
    checks = await asyncio.gather(*(is_telegram_owner(bot, cid, user_id) for cid, _ in candidates))
    return [{"id": cid, "title": title or f"Чат {cid}"} for (cid, title), ok in zip(candidates, checks) if ok]
