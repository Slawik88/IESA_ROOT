# bot/middlewares/purge_gate_mw.py — admin_audit B5: режим письма во время чистки.
#
# Если в чате активна чистка (is_purging) и владелец настроил purge_write_rank > 0,
# писать могут только участники с рангом ≥ purge_write_rank (Владелец, ранг 6 —
# всегда). Сообщения остальных бот тихо удаляет. Telegram не умеет пер-ранговые
# ограничения нативно — поэтому enforcement на стороне бота.
#
# Производительность: TTL-кэш purge-состояния чатов (30с) — вне режима чистки
# это один лёгкий SELECT на чат раз в 30 секунд, не на каждое сообщение.
import time
from typing import Callable, Awaitable, Dict, Any

from aiogram.types import TelegramObject
from loguru import logger

_CACHE: dict[int, tuple[bool, int, float]] = {}   # chat_id -> (is_purging, write_rank, expires)
_TTL = 30.0


def purge_gate_invalidate(chat_id: int) -> None:
    """Сброс кэша при старте/завершении чистки (вызывать не обязательно —
    TTL 30с сам подхватит, но со сбросом режим включается мгновенно)."""
    _CACHE.pop(chat_id, None)


async def _purge_state(db, chat_id: int) -> tuple[bool, int]:
    now = time.monotonic()
    hit = _CACHE.get(chat_id)
    if hit and hit[2] > now:
        return hit[0], hit[1]
    async with db.execute(
        "SELECT COALESCE(is_purging, FALSE), COALESCE(purge_write_rank, 0) "
        "FROM chat_settings WHERE chat_id = ?",
        (chat_id,),
    ) as c:
        row = await c.fetchone()
    is_purging = bool(row[0]) if row else False
    write_rank = int(row[1]) if row else 0
    _CACHE[chat_id] = (is_purging, write_rank, now + _TTL)
    return is_purging, write_rank


async def purge_gate_middleware(
    handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
    event: TelegramObject,
    data: Dict[str, Any],
) -> Any:
    msg = getattr(event, "message", None)
    chat = getattr(msg, "chat", None)
    user = getattr(msg, "from_user", None)
    # Только обычные сообщения в группах; кнопки/сервисные апдейты не трогаем
    if not msg or not chat or not user or chat.type == "private" or user.is_bot:
        return await handler(event, data)

    db = data.get("db")
    if db is None:
        return await handler(event, data)

    try:
        is_purging, write_rank = await _purge_state(db, chat.id)
        if not is_purging or write_rank <= 0:
            return await handler(event, data)

        developer_id = data.get("developer_id") or 0
        if developer_id and user.id == developer_id:
            return await handler(event, data)

        async with db.execute(
            "SELECT COALESCE(local_rank, 0) FROM user_chat_stats "
            "WHERE user_tg_id = ? AND chat_tg_id = ?",
            (user.id, chat.id),
        ) as c:
            row = await c.fetchone()
        rank = int(row[0]) if row else 0
        if rank >= write_rank or rank >= 6:   # Владелец пишет всегда
            return await handler(event, data)

        try:
            await msg.delete()
        except Exception:
            pass   # нет прав на удаление — не роняем обработку
        return  # сообщение подавлено, хендлеры не вызываются
    except Exception as e:
        logger.debug(f"purge gate error: {e}")
        return await handler(event, data)
