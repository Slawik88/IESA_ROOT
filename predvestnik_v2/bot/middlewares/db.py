import time
from typing import Callable, Awaitable, Dict, Any
from aiogram.types import TelegramObject

from core import ops_metrics
from infrastructure.database import get_pool
from infrastructure.pg_adapter import PGAdapter


async def db_middleware(
    handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
    event: TelegramObject,
    data: Dict[str, Any],
) -> Any:
    # Чат-логика (учёт сообщений, санкции, антиспам, чистка) удалена из кода;
    # данные остаются в БД. Здесь только соединение для будущих обработчиков.
    started = time.perf_counter()
    async with get_pool().acquire() as conn:
        ops_metrics.observe("pool_wait", "bot", (time.perf_counter() - started) * 1000)
        data["db"] = PGAdapter(conn)
        return await handler(event, data)
