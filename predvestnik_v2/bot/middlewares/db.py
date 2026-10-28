from typing import Callable, Awaitable, Dict, Any

from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.types import TelegramObject

from infrastructure import lazy_db
from infrastructure.database import get_pool


async def db_middleware(
    handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
    event: TelegramObject,
    data: Dict[str, Any],
) -> Any:
    # The connection is taken on the handler's first SQL and given back before each Telegram call
    # (DbReleaseMiddleware below), so a slow Telegram never holds a pool connection.
    async with lazy_db.lazy_connection(get_pool(), source="bot") as db:
        data["db"] = db
        return await handler(event, data)


class DbReleaseMiddleware(BaseRequestMiddleware):
    """Outbound (Bot.session) middleware: before any Telegram request, return the idle connection of the
    current update or request to the pool. Registered outside the throttler, so the send-slot wait is free too."""

    async def __call__(self, make_request, bot, method):
        await lazy_db.release_current()
        return await make_request(bot, method)
