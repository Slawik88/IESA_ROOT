import os
import time
from typing import Callable, Awaitable, Dict, Any
from aiogram.types import TelegramObject
from loguru import logger

from bot.config import config
from infrastructure.database import get_pool
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import users
from infrastructure.repositories.streak import get_chat_timezone
from services import leveling

anti_spam_cache: dict[int, float] = {}

async def _safe_send(bot, chat_id: int, text: str) -> None:
    """Обёртка для fire-and-forget отправок: без неё исключение в задаче,
    запущенной через asyncio.ensure_future без await, никогда не забирается —
    попадает в лог как 'Task exception was never retrieved' и просто теряется."""
    try:
        await bot.send_message(chat_id, text, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Fire-and-forget send to {chat_id} failed: {e}")


def _notify_ai_hint(bot, chat_id: int, user) -> None:
    """Discovery-полиш 2026-07-19: разовая подсказка про ИИ-помощника после
    30-го сообщения новичка в чате (fire-and-forget)."""
    import asyncio
    if not bot:
        return
    text = "🤖 Кстати — если что-то не понятно, просто напиши «бот, [вопрос]» — отвечу как помощник"
    asyncio.ensure_future(_safe_send(bot, chat_id, text))


async def db_middleware(
    handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
    event: TelegramObject,
    data: Dict[str, Any],
) -> Any:
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        data["db"] = db

        user = data.get("event_from_user")
        chat_obj = data.get("event_chat")
        # Другие боты в группе (модерация/статистика/т.п.) тоже шлют текстовые
        # сообщения — без этой проверки они регистрировались как игроки и качали
        # уровень/XP на общих основаниях (найдено при сверке миграции уровней
        # 2026-07-03: посторонние ID в списке на выдачу «Пакета Обновления 2.0»).
        is_bot_sender = bool(user and getattr(user, "is_bot", False))

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

            if user and not is_bot_sender:
                await users.update_user(db, user.id, user.username)
                if config.developer_id and user.id == config.developer_id:
                    await db.execute(
                        "UPDATE users SET global_rank = 3 "
                        "WHERE user_tg_id = ? AND global_rank != 3",
                        (user.id,),
                    )

            # Только групповые чаты порождают chat_settings/статистику. Личка с ботом
            # (type='private', положительный chat_id, title=None) НЕ должна создавать
            # строк chat_settings — иначе в админ-панелях появляются «фантомные чаты-цифры».
            _is_group = getattr(chat_obj, "type", None) in ("group", "supergroup") if chat_obj else False

            if user and not is_bot_sender and chat_obj and event.message and _is_group:
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

                try:
                    _tz_int = await get_chat_timezone(db, chat_obj.id)
                except Exception:
                    _tz_int = 0
                _sign = "+" if _tz_int >= 0 else "-"
                _tz = f"{_sign}{abs(_tz_int)} hours"

                # Сообщение учитывается только как статистика активности. Старые
                # XP/уровни, задания и ачивки больше не растут от объёма текста.
                _, _, _msg_count = await leveling.process_message_xp(
                    db, user.id, chat_obj.id, _tz
                )

                # Discovery-полиш 2026-07-19: разовая подсказка про ИИ-помощника
                # после 30-го сообщения новичка в чате (см. spec в docs/superpowers).
                if _msg_count == 30 and os.getenv("GEMINI_API_KEY"):
                    try:
                        from services.ai_hint import mark_ai_hint_shown
                        if await mark_ai_hint_shown(db, user.id):
                            _notify_ai_hint(data.get("bot"), chat_obj.id, user)
                    except Exception:
                        pass

        except Exception as e:
            # Сбой в трекинге (XP/квесты/ачивки/чат-статы) НЕ должен блокировать сам
            # хендлер команды — логируем и идём дальше без него. ВАЖНО: handler()
            # вызывается ровно один раз, СНАРУЖИ этого try — раньше он был внутри,
            # и любое исключение из handler() (например TelegramRetryAfter при
            # message.answer() под flood control) тоже ловилось здесь и запускало
            # handler() ПОВТОРНО, задваивая побочные эффекты (квестовые метрики,
            # начисления) и давая в логе парные traceback'и ("During handling of
            # the above exception..."), при этом ничего не чиня — вторая попытка
            # падала с той же ошибкой сразу же.
            logger.error(f"DB middleware setup error: {e}")

        return await handler(event, data)
