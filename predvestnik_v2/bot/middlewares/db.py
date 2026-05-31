import time
import aiosqlite
from typing import Callable, Awaitable, Dict, Any
from aiogram.types import TelegramObject
from loguru import logger

from bot.config import config
from infrastructure.repositories import users
from services import leveling

# Кэш анти-спама (user_id -> timestamp)
anti_spam_cache = {}

async def db_middleware(
    handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
    event: TelegramObject,
    data: Dict[str, Any]
) -> Any:
    async with aiosqlite.connect(config.db_path, timeout=20.0) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=10000")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("PRAGMA cache_size=-32000")
        
        user = data.get("event_from_user")
        chat_obj = data.get("event_chat")

        try:
            # C1-C: Global blacklist — check FIRST, before everything else
            if user or chat_obj:
                blocked = False
                if user:
                    async with db.execute(
                        "SELECT 1 FROM global_blacklist WHERE entity_type='user' AND entity_id=?",
                        (user.id,),
                    ) as _c:
                        blocked = (await _c.fetchone()) is not None
                if not blocked and chat_obj:
                    async with db.execute(
                        "SELECT 1 FROM global_blacklist WHERE entity_type='chat' AND entity_id=?",
                        (chat_obj.id,),
                    ) as _c:
                        blocked = (await _c.fetchone()) is not None
                if blocked:
                    return

            if user:
                await users.update_user(db, user.id, user.username)
                # Ensure developer always has global_rank = 3.
                # MUST commit here — otherwise the implicit sqlite3 transaction
                # stays open and causes "cannot start a transaction within a
                # transaction" when the chest/other handlers use BEGIN IMMEDIATE.
                if config.developer_id and user.id == config.developer_id:
                    await db.execute(
                        "UPDATE users SET global_rank = 3 "
                        "WHERE user_tg_id = ? AND global_rank != 3",
                        (user.id,),
                    )
                    await db.commit()

            # Only process XP/stats for real message updates.
            # At dp.update level: Update.message is set for messages, None for callbacks.
            if user and chat_obj and event.message:
                # --- ЛОГИКА БЛОКИРОВКИ ПРИ ЧИСТКЕ ---
                async with db.execute("SELECT is_purging, purge_min_rank FROM chat_settings WHERE chat_id = ?", (chat_obj.id,)) as cursor:
                    settings = await cursor.fetchone()
                
                if settings and settings['is_purging'] == 1:
                    async with db.execute("SELECT local_rank FROM user_chat_stats WHERE user_tg_id = ? AND chat_tg_id = ?", (user.id, chat_obj.id)) as cursor:
                        stats = await cursor.fetchone()
                        rank = stats['local_rank'] if stats else 0
                        
                    # Если ранг меньше требуемого (обычно 4) и это не разработчик
                    if rank < settings['purge_min_rank'] and user.id != config.developer_id:
                        try:
                            await event.message.delete()
                            # Анти-спам предупреждений (раз в 30 секунд на человека)
                            now = time.time()
                            if now - anti_spam_cache.get(user.id, 0) > 30:
                                anti_spam_cache[user.id] = now
                                await event.message.answer(f"🤫 Тссс, <a href='tg://user?id={user.id}'>{user.first_name}</a>! Идет глобальная чистка чата. Подождите.", parse_mode="HTML")
                        except Exception:
                            pass
                        return # Останавливаем обработку сообщения!

                # 1. Выдача XP
                await leveling.process_message_xp(db, user.id, chat_obj.id, config.timezone_offset)
                
                # 2. Инициализация настроек чата (с обновлением названия)
                chat_title = getattr(chat_obj, "title", None)
                await db.execute(
                    "INSERT INTO chat_settings (chat_id, chat_title) VALUES (?, ?) "
                    "ON CONFLICT(chat_id) DO UPDATE SET chat_title = excluded.chat_title",
                    (chat_obj.id, chat_title),
                )
                
                # 3. Запись в ежедневную статистику
                tz = config.timezone_offset
                query_daily = """
                    INSERT INTO daily_user_stats (user_id, chat_id, date, message_count)
                    VALUES (?, ?, strftime('%Y-%m-%d', 'now', ?), 1)
                    ON CONFLICT(user_id, chat_id, date) 
                    DO UPDATE SET message_count = message_count + 1
                """
                await db.execute(query_daily, (user.id, chat_obj.id, tz))
                await db.commit()
                
            data["db"] = db
            return await handler(event, data)
            
        except Exception as e:
            logger.error(f"Ошибка в Middleware при работе с БД: {e}")
            return await handler(event, data)