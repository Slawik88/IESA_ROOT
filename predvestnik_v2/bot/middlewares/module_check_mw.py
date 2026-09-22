"""
bot/middlewares/module_check_mw.py
C2: Per-router middleware that checks if a module is enabled in this chat.
Usage (in each handler file):
    from bot.middlewares.module_check_mw import ModuleCheckMiddleware
    router.message.middleware(ModuleCheckMiddleware("module_shop"))
"""
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from core.chat_modules import CHAT_MODULE_KEYS, chat_module_default


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
