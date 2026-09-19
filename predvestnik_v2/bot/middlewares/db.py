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
from bot.middlewares.global_sanctions_mw import evaluate_global_sanctions

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

        # This must run before *any* automatic writer below.  A failure is
        # fail-closed: logging it and continuing would let a banned user alter
        # activity-derived state while sanction storage is unavailable.
        try:
            if not await evaluate_global_sanctions(db, event, data):
                return
        except Exception as exc:
            logger.error(f"Global-sanction gate failed closed: {exc}")
            return

        # Appeals/help from a banned user are deliberately allowed to reach
        # their handlers, but must not refresh profile/activity automatically.
        automatic_writes_allowed = not bool(data.get("user_banned"))

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

            if user and not is_bot_sender and automatic_writes_allowed:
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

            if (
                user
                and not is_bot_sender
                and automatic_writes_allowed
                and chat_obj
                and event.message
                and _is_group
            ):
                # Mafia's phase gate is evaluated before this middleware counts
                # ordinary activity. During discussion only living players may
                # speak; at night/voting only everyone else may speak. This is
                # intentionally separate from the old purge mechanics.
                from services import mafia_v1 as _mafia
                from infrastructure.repositories import system_flags as _system_flags
                _topic_id = getattr(event.message, "message_thread_id", None)
                _gate = "allow"
                if await _system_flags.is_enabled(db, "game_mafia_v1"):
                    _gate = await _mafia.message_gate(
                        db, chat_id=int(chat_obj.id), topic_id=_topic_id, user_id=int(user.id)
                    )
                if _gate == "suppress":
                    try:
                        await event.message.delete()
                    except Exception:
                        # Lost delete rights mean we must not silently continue
                        # claiming a protected phase. Pause instead of changing
                        # any group permissions or overriding moderation.
                        from infrastructure.repositories import mafia_v1 as _mafia_repo
                        _active = await _mafia_repo.active_match(db, chat_id=int(chat_obj.id), topic_id=_topic_id)
                        if _active:
                            await _mafia.pause_for_moderation_intervention(db, match_id=int(_active["id"]))
                            # Show the durable pause immediately; otherwise a
                            # stale "night" card leaves players guessing why
                            # their messages disappeared.
                            try:
                                from bot.handlers.mafia_v1 import publish_phase
                                _view = await _mafia.current_view(db, match_id=int(_active["id"]))
                                if _view and data.get("bot"):
                                    await publish_phase(data["bot"], db, _view)
                            except Exception as _mafia_pause_card_error:
                                logger.debug(f"Mafia pause card update failed: {_mafia_pause_card_error}")
                        return await handler(event, data)
                    return

                async with db.execute(
                    "SELECT is_purging, purge_min_rank FROM chat_settings WHERE chat_id = ?",
                    (chat_obj.id,),
                ) as cursor:
                    settings = await cursor.fetchone()

                if settings and settings["is_purging"]:
                    # A purge and a game gate cannot safely control the same
                    # messages at once. Preserve both systems' state: the
                    # purge continues under its own rules and the active game
                    # pauses before it can claim a protected phase.
                    if await _system_flags.is_enabled(db, "game_mafia_v1"):
                        from infrastructure.repositories import mafia_v1 as _mafia_repo
                        _active = await _mafia_repo.active_match(db, chat_id=int(chat_obj.id), topic_id=_topic_id)
                        if _active:
                            await _mafia.pause_for_moderation_intervention(db, match_id=int(_active["id"]))
                            try:
                                from bot.handlers.mafia_v1 import publish_phase
                                _view = await _mafia.current_view(db, match_id=int(_active["id"]))
                                if _view and data.get("bot"):
                                    await publish_phase(data["bot"], db, _view)
                            except Exception as _mafia_pause_card_error:
                                logger.debug(f"Mafia purge pause card update failed: {_mafia_pause_card_error}")
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

                # Every tenth ordinary human message moves the lobby card to
                # the bottom without creating a second match or resetting its
                # settings. Sending happens only after activity persistence.
                _lobby = await _mafia.note_lobby_human_message(
                    db, chat_id=int(chat_obj.id), topic_id=_topic_id
                ) if await _system_flags.is_enabled(db, "game_mafia_v1") else None
                if _lobby and data.get("bot"):
                    try:
                        from bot.handlers.mafia_v1 import _lobby_keyboard, _lobby_text
                        sent = await data["bot"].send_message(
                            int(chat_obj.id), _lobby_text(_lobby),
                            reply_markup=_lobby_keyboard(_lobby), parse_mode="HTML",
                            message_thread_id=_topic_id,
                        )
                        from infrastructure.repositories import mafia_v1 as _mafia_repo
                        await _mafia_repo.bind_lobby_message(db, match_id=int(_lobby["match_id"]), message_id=int(sent.message_id))
                    except Exception as _mafia_repost_error:
                        logger.debug(f"Mafia lobby repost failed: {_mafia_repost_error}")

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
