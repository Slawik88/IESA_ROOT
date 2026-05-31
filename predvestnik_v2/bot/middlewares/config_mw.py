from typing import Callable, Awaitable, Dict, Any
from aiogram.types import TelegramObject

from bot.config import config


async def config_middleware(
    handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
    event: TelegramObject,
    data: Dict[str, Any],
) -> Any:
    data["developer_id"] = config.developer_id
    data["timezone_offset"] = config.timezone_offset
    return await handler(event, data)
