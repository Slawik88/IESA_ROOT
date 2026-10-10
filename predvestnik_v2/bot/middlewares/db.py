from typing import Callable, Awaitable, Dict, Any
from aiogram.types import TelegramObject

from infrastructure.database import get_pool
from infrastructure.pg_adapter import PGAdapter


async def db_middleware(
    handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
    event: TelegramObject,
    data: Dict[str, Any],
) -> Any:
    # Чат-логика (учёт сообщений, санкции, антиспам, чистка) удалена из кода;
    # данные остаются в БД. Здесь только соединение для будущих обработчиков.
    async with get_pool().acquire() as conn:
        data["db"] = PGAdapter(conn)
        return await handler(event, data)
