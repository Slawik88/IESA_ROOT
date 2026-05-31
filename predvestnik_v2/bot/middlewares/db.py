import time
from typing import Callable, Awaitable, Dict, Any
from aiogram.types import TelegramObject
from loguru import logger

from infrastructure.database import get_pool
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import users
from services import leveling

anti_spam_cache: dict[int, float] = {}


async def db_middleware(
    handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
    event: TelegramObject,
    data: Dict[str, Any],
) -> Any:
    from bot.config import config

    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)

        user = data.get("event_from_user")
        chat_obj = data.get("event_chat")

        try:
            if user or chat_obj:
                blocked = False
                if user:
                    async with db.execute(
                        "SELECT 1 FROM global_blacklist WHERE entity_type='user' AND entity_id=?",
                        (user.id,),
                    ) as c:
                        blocked = (await c.fetchone()) is not None
                if not blocked and chat_obj:
                    async with db.execute(
                        "SELECT 1 FROM global_blacklist WHERE entity_type='chat' AND entity_id=?",
                        (chat_obj.id,),
                    ) as c:
                        blocked = (await c.fetchone()) is not None
                if blocked:
                    return

            if user:
                await users.update_user(db, user.id, user.username)
                if config.developer_id and user.id == config.developer_id:
                    await db.execute(
                        "UPDATE users SET global_rank = 3 "
                        "WHERE user_tg_id = ? AND global_rank != 3",
                        (user.id,),
                    )

            if user and chat_obj and event.message:
                async with db.execute(
                    "SELECT is_purging, purge_min_rank FROM chat_settings WHERE chat_id = ?",
                    (chat_obj.id,),
                ) as cursor:
                    settings = await cursor.fetchone()

                if settings and settings["is_purging"]:
                    async with db.execute(
                        "SELECT local_rank FROM user_chat_stats "
                        "WHERE user_tg_id = ? AND chat_tg_id = ?",
                        (user.id, chat_obj.id),
                    ) as cursor:
                        stats = await cursor.fetchone()
                    rank = stats["local_rank"] if stats else 0
                    if rank < settings["purge_min_rank"] and user.id != config.developer_id:
                        try:
                            await event.message.delete()
                            now = time.time()
                            if now - anti_spam_cache.get(user.id, 0) > 30:
                                anti_spam_cache[user.id] = now
                                await event.message.answer(
                                    f'🤫 Тссс, <a href="tg://user?id={user.id}">'
                                    f"{user.first_name}</a>! Идет глобальная чистка чата. Подождите.",
                                    parse_mode="HTML",
                                )
                        except Exception:
                            pass
                        return

                await leveling.process_message_xp(
                    db, user.id, chat_obj.id, config.timezone_offset
                )

                chat_title = getattr(chat_obj, "title", None)
                await db.execute(
                    "INSERT INTO chat_settings (chat_id, chat_title) VALUES (?, ?) "
                    "ON CONFLICT(chat_id) DO UPDATE SET chat_title = EXCLUDED.chat_title",
                    (chat_obj.id, chat_title),
                )

                await db.execute(
                    "INSERT INTO daily_user_stats (user_id, chat_id, date, message_count) "
                    "VALUES (?, ?, TO_CHAR(NOW() + ?::INTERVAL, 'YYYY-MM-DD'), 1) "
                    "ON CONFLICT(user_id, chat_id, date) "
                    "DO UPDATE SET message_count = daily_user_stats.message_count + 1",
                    (user.id, chat_obj.id, config.timezone_offset),
                )

            data["db"] = db
            return await handler(event, data)

        except Exception as e:
            logger.error(f"DB middleware error: {e}")
            return await handler(event, data)
