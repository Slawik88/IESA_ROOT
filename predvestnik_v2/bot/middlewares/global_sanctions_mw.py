# bot/middlewares/global_sanctions_mw.py
# Глобальные баны/ограничения экосистемы бота (Implementation Block 6.4).

from typing import Callable, Awaitable, Dict, Any
from aiogram.types import TelegramObject

from infrastructure.repositories.users import get_global_rank
from services import global_moderation
from services.roles import DEVELOPER_GLOBAL_RANK


async def global_sanctions_middleware(
    handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
    event: TelegramObject,
    data: Dict[str, Any],
) -> Any:
    db = data["db"]
    user = data.get("event_from_user")
    chat_obj = data.get("event_chat")

    if user:
        actor_rank = await get_global_rank(db, user.id)
        if actor_rank >= DEVELOPER_GLOBAL_RANK:
            return await handler(event, data)  # Разработчик — иммунитет

        if await global_moderation.is_user_banned(db, user.id):
            return  # бот молчит везде

    if chat_obj:
        if await global_moderation.is_chat_banned(db, chat_obj.id):
            return  # бот молчит

        data["chat_restricted"] = await global_moderation.get_chat_restriction(db, chat_obj.id)

    if user:
        data["user_restricted"] = await global_moderation.get_user_restriction(db, user.id)

    return await handler(event, data)
