"""Fail-closed Telegram update gate for the isolated public preprod bot."""

from typing import Any, Awaitable, Callable, Dict

from aiogram.types import TelegramObject, Update
from loguru import logger

from infrastructure.preprod import is_preprod, require_preprod_user


async def preprod_gate_middleware(
    handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
    event: TelegramObject,
    data: Dict[str, Any],
) -> Any:
    if not is_preprod():
        return await handler(event, data)

    user = data.get("event_from_user") or getattr(event, "from_user", None)
    user_id = getattr(user, "id", None)
    if user is None:   # запрос виджета aiogram не разбирает: автор лежит в сыром поле
        from bot.middlewares.widget_query import widget_payload
        found = widget_payload(event) if isinstance(event, Update) else None
        sender = found[1].get("from") if found else None
        user_id = sender.get("id") if isinstance(sender, dict) else None
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        logger.warning("Preprod ignored Telegram update without a valid numeric actor")
        return None
    if not require_preprod_user(user_id):
        logger.warning("Preprod ignored Telegram update from non-allowlisted user {}", user_id)
        return None
    return await handler(event, data)
