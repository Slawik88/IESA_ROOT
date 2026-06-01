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

                # Ensure chat_settings row exists, then read the chat-local
                # timezone — single source of truth for ALL date buckets
                # (level/day/week/month counters → tops, daily stats, quests).
                chat_title = getattr(chat_obj, "title", None)
                await db.execute(
                    "INSERT INTO chat_settings (chat_id, chat_title) VALUES (?, ?) "
                    "ON CONFLICT(chat_id) DO UPDATE SET chat_title = EXCLUDED.chat_title",
                    (chat_obj.id, chat_title),
                )

                from infrastructure.repositories.streak import get_chat_timezone
                try:
                    _tz_int = await get_chat_timezone(db, chat_obj.id)
                except Exception:
                    _tz_int = 0
                _sign = "+" if _tz_int >= 0 else "-"
                _tz = f"{_sign}{abs(_tz_int)} hours"

                # Rolling per-day/week/month counters (used by «бот топ») now
                # reset at the CHAT-local boundary, not a global config tz.
                await leveling.process_message_xp(
                    db, user.id, chat_obj.id, _tz
                )

                await db.execute(
                    "INSERT INTO daily_user_stats (user_id, chat_id, date, message_count) "
                    f"VALUES (?, ?, TO_CHAR(NOW() + INTERVAL '{_tz}', 'YYYY-MM-DD'), 1) "
                    "ON CONFLICT(user_id, chat_id, date) "
                    "DO UPDATE SET message_count = daily_user_stats.message_count + 1",
                    (user.id, chat_obj.id),
                )

                # Daily quest: messages_in_chat_today (most common quest metric).
                # No-op if the user has not opened «бот задания» today.
                try:
                    from services.quests import increment_metric as _quest_incr
                    await _quest_incr(db, user.id, chat_obj.id, "messages_in_chat_today", delta=1.0)
                except Exception:
                    pass

            data["db"] = db
            return await handler(event, data)

        except Exception as e:
            logger.error(f"DB middleware error: {e}")
            # Only forward to handler if db was successfully injected —
            # calling handler without db causes TypeError in every command.
            if "db" in data:
                return await handler(event, data)
