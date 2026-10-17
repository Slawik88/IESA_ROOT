"""
bot/middlewares/module_check_mw.py
C2: Per-router middleware that checks if a module is enabled in this chat.
Usage (in each handler file):
    from bot.middlewares.module_check_mw import ModuleCheckMiddleware
    router.message.middleware(ModuleCheckMiddleware("module_games"))
"""
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from loguru import logger

from core.chat_modules import CHAT_MODULE_KEYS, MASTER_CHAT_MODULE, chat_module_default


async def module_disabled_reason(db, chat_id: int, module_key: str) -> str | None:
    """Return the effective disable reason from the canonical two-level policy."""
    if module_key not in CHAT_MODULE_KEYS:
        raise ValueError(f"unknown chat module: {module_key}")
    async with db.execute(
        f"SELECT {module_key} FROM chat_settings WHERE chat_id = ?",
        (chat_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row is not None and row[0] == 0:
        return "Этот раздел временно недоступен в данном чате."
    async with db.execute(
        "SELECT enabled, disabled_reason FROM global_module_toggles WHERE module_key = ?",
        (module_key,),
    ) as cursor:
        row = await cursor.fetchone()
    globally_enabled = bool(row[0]) if row is not None else chat_module_default(module_key)
    if not globally_enabled:
        if row is None:
            return "Этот раздел пока не включён глобально."
        return str(row[1] or "Этот раздел временно отключён глобально.")
    return None


class ModuleCheckMiddleware(BaseMiddleware):
    def __init__(self, module_key: str) -> None:
        if module_key not in CHAT_MODULE_KEYS:
            raise ValueError(f"unknown chat module: {module_key}")
        self.module_key = module_key

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        db = data.get("db")
        chat = data.get("event_chat")

        if db and chat:
            reason = await module_disabled_reason(db, int(chat.id), self.module_key)
            if reason:
                if isinstance(event, Message):
                    await event.answer(f"🔧 {reason}")
                elif isinstance(event, CallbackQuery):
                    await event.answer(f"🔧 {reason}", show_alert=True)
                return

        return await handler(event, data)


# ── Мастер-тумблер «Весь бот в чатах» ─────────────────────────────────────────
# Когда module_bot выключен (в чате или глобально), бот тихо игнорирует команды
# и кнопки в этом чате: ни ответов, ни подсказок. Административные механики
# (удаление при чистке, санкции) выполняются раньше и не затрагиваются.
# TTL-кэш (30с) — как в purge_gate_mw: не гонять 2 запроса на каждое сообщение.

_SILENCE_CACHE: dict[int, tuple[bool, float]] = {}
_SILENCE_TTL = 30.0


def bot_silence_invalidate(chat_id: int) -> None:
    """Сброс кэша тишины чата (например, сразу после переключения модуля)."""
    _SILENCE_CACHE.pop(int(chat_id), None)


async def _chat_is_silenced(db, chat_id: int) -> bool:
    now = time.monotonic()
    hit = _SILENCE_CACHE.get(chat_id)
    if hit and hit[1] > now:
        return hit[0]
    try:
        silenced = bool(await module_disabled_reason(db, chat_id, MASTER_CHAT_MODULE))
    except Exception as e:
        # Fail-open: ошибка БД не должна превращаться в глобальное молчание.
        logger.debug(f"bot silence check failed for chat {chat_id}: {e}")
        silenced = False
    _SILENCE_CACHE[chat_id] = (silenced, now + _SILENCE_TTL)
    return silenced


async def bot_silence_middleware(
    handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
    event: TelegramObject,
    data: Dict[str, Any],
) -> Any:
    """Update-level gate (dp.update): тихий стоп команд и кнопок в чате.

    Как и purge_gate_mw, смотрит вложенные message/callback_query у Update.
    """
    db = data.get("db")
    if db is None:
        return await handler(event, data)

    cb = getattr(event, "callback_query", None)
    if cb is not None:
        cb_msg = getattr(cb, "message", None)
        chat = getattr(cb_msg, "chat", None)
        if chat is None or chat.type == "private":
            return await handler(event, data)
        if await _chat_is_silenced(db, int(chat.id)):
            try:
                await cb.answer()   # тихо гасим «часики», без текста
            except Exception as e:
                logger.debug(f"bot silence: callback answer skipped: {e}")
            return
        return await handler(event, data)

    msg = getattr(event, "message", None)
    if msg is None:
        return await handler(event, data)
    chat = getattr(msg, "chat", None)
    user = getattr(msg, "from_user", None)
    if not chat or chat.type == "private" or user is None or user.is_bot:
        return await handler(event, data)
    if await _chat_is_silenced(db, int(chat.id)):
        return
    return await handler(event, data)
