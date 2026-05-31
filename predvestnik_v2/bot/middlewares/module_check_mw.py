"""
bot/middlewares/module_check_mw.py
C2: Per-router middleware that checks if a module is enabled in this chat.
Usage (in each handler file):
    from bot.middlewares.module_check_mw import ModuleCheckMiddleware
    router.message.middleware(ModuleCheckMiddleware("module_shop"))
"""
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject


class ModuleCheckMiddleware(BaseMiddleware):
    def __init__(self, module_key: str) -> None:
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
            # Per-chat check
            async with db.execute(
                f"SELECT {self.module_key} FROM chat_settings WHERE chat_id = ?",
                (chat.id,),
            ) as c:
                row = await c.fetchone()
            if row is not None and row[0] == 0:
                if isinstance(event, Message):
                    await event.answer("🔧 Этот раздел временно недоступен в данном чате.")
                return

            # Global check
            async with db.execute(
                "SELECT enabled FROM global_module_toggles WHERE module_key = ?",
                (self.module_key,),
            ) as c:
                grow = await c.fetchone()
            if grow is not None and grow[0] == 0:
                if isinstance(event, Message):
                    await event.answer("🔧 Этот раздел временно отключён глобально.")
                return

        return await handler(event, data)
