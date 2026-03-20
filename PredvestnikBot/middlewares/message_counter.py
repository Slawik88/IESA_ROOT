import asyncio
import re
import time
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot
from aiogram.types import ChatPermissions, Message

from config import (
    DEFAULT_ANTIFLOOD_ACTION, DEFAULT_ANTIFLOOD_ENABLED, DEFAULT_ANTIFLOOD_LIMIT,
    DEFAULT_BLACKLIST_ENABLED, DEFAULT_FLOOD_MUTE, DEVELOPER_ID, FLOOD_WINDOW,
    LEVEL_UP_ANNOUNCE, XP_COOLDOWN, XP_PER_MESSAGE,
    BLACKLIST_USE_MORPHOLOGY,
)
from database.db import (
    add_xp_in_chat, get_blacklist, get_chat_settings, get_filters, get_locks,
    get_todays_quest, get_user_stats, increment_cleanup_count,
    increment_message_count_chat, is_group_allowed,
    mark_quest_rewarded, quest_tick,
    upsert_chat, upsert_user, upsert_user_stats,
)
from utils.flood import check_flood, check_spam
from utils.helpers import user_mention
from utils.ranks import rank_level

# ─── pymorphy3 для морфологии чёрного списка ─────────────────────────────────
_morph = None
_word_re = re.compile(r'[а-яёa-z0-9]+', re.IGNORECASE)

def _get_morph():
    global _morph
    if _morph is None:
        import pymorphy3
        _morph = pymorphy3.MorphAnalyzer()
    return _morph

def _lemmatize(word: str) -> str:
    return _get_morph().parse(word)[0].normal_form

def _check_blacklist_morph(text_lower: str, blacklist) -> bool:
    words = _word_re.findall(text_lower)
    lemmas = {_lemmatize(w) for w in words}
    for row in blacklist:
        bl_lemma = _lemmatize(row["word"].lower())
        if bl_lemma in lemmas:
            return True
    return False

# Кэш: (chat_id, user_id) -> timestamp последней проверки статуса
_checked: dict[tuple[int, int], float] = {}
_CHECKED_TTL = 3600.0  # перепроверять раз в час

# Кулдаун XP: (user_id, chat_id) -> timestamp последнего начисления
_xp_cooldown: dict[tuple[int, int], float] = {}


async def _delete_after(msg, delay: int = 5) -> None:
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass

_URL_RE = re.compile(
    r"(https?://|www\.|t\.me/|tg://|telegram\.me/)", re.IGNORECASE
)


class AutoModMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        user = event.from_user
        if not user or user.is_bot:
            return await handler(event, data)

        # 0. Белый список групп — если включён, игнорируем неразрешённые группы
        #    (разработчик всегда проходит, чтобы мог добавить группу)
        if event.chat.type in ("group", "supergroup"):
            if not is_group_allowed(event.chat.id) and user.id != DEVELOPER_ID:
                return
            # Админ-группы — только для системных уведомлений, без статистики/авто-мода
            from database.db import get_admin_group_ids
            if event.chat.id in get_admin_group_ids():
                return await handler(event, data)

        # 1. Регистрация / обновление пользователя
        await upsert_user(user.id, user.username or "", user.full_name or "")

        await upsert_chat(
            event.chat.id,
            getattr(event.chat, "title", "") or getattr(event.chat, "full_name", ""),
            getattr(event.chat, "username", "") or "",
            event.chat.type,
            1,
        )

        in_group = event.chat.type in ("group", "supergroup")

        # 2. Per-chat profile + подсчёт сообщений (только в группах)
        if in_group:
            await upsert_user_stats(user.id, event.chat.id)
            await increment_message_count_chat(user.id, event.chat.id)
            await increment_cleanup_count(event.chat.id, user.id)

            # Quest progress ("messages" type)
            quest = get_todays_quest()
            if quest["type"] == "messages":
                from datetime import date as _date
                _today = _date.today().isoformat()
                new_p, goal, just_done = await quest_tick(
                    user.id, event.chat.id, _today, quest["type"], quest["goal"],
                )
                if just_done:
                    await add_xp_in_chat(user.id, event.chat.id, quest["xp"])
                    await mark_quest_rewarded(user.id, event.chat.id, _today)
                    try:
                        await event.answer(
                            f"🎉 {user_mention(user.id, user.full_name)} выполнил ежедневное задание! "
                            f"<b>+{quest['xp']} XP</b>",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

            # XP раз в минуту (per-chat)
            now = time.monotonic()
            # Очищаем просроченные записи (выборочно, не полная очистка)
            xp_key = (user.id, event.chat.id)
            if len(_xp_cooldown) > 500:
                cutoff = now - XP_COOLDOWN * 2
                expired = [k for k, v in _xp_cooldown.items() if v <= cutoff]
                for k in expired:
                    del _xp_cooldown[k]
            if now - _xp_cooldown.get(xp_key, 0) >= XP_COOLDOWN:
                _xp_cooldown[xp_key] = now
                new_xp, new_level, leveled_up = await add_xp_in_chat(user.id, event.chat.id, XP_PER_MESSAGE)
                if leveled_up and LEVEL_UP_ANNOUNCE:
                    try:
                        await event.answer(
                            f"🌟 {user_mention(user.id, user.full_name)} достиг <b>{new_level} уровня</b>! "
                            f"(XP: {new_xp})",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

        # 3. Проверка статуса выполняется без авто-повышений (все ранги выдаются вручную)
        if in_group:
            key = (event.chat.id, user.id)
            now_mono = time.monotonic()
            if key not in _checked or now_mono - _checked[key] > _CHECKED_TTL:
                _checked[key] = now_mono
                # Периодическая очистка устаревших записей
                if len(_checked) > 1000:
                    cutoff = now_mono - _CHECKED_TTL
                    expired = [k for k, v in _checked.items() if v <= cutoff]
                    for k in expired:
                        del _checked[k]

        # Авто-мод только в группах
        if not in_group:
            return await handler(event, data)

        stats = await get_user_stats(user.id, event.chat.id)
        user_rank = stats["rank"] if stats else "user"

        # Модераторы и выше освобождены от авто-мода
        if rank_level(user_rank) >= rank_level("moderator"):
            return await handler(event, data)

        bot_: Bot = data["bot"]
        chat_id = event.chat.id

        # 4а. Авто-детект спама: > 3 сообщений за 1 секунду → мут 5 минут (всегда включён)
        if check_spam(chat_id, user.id, 3, 1.0):
            try:
                await event.delete()
                until = datetime.now() + timedelta(seconds=DEFAULT_FLOOD_MUTE)
                await bot_.restrict_chat_member(
                    chat_id, user.id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until,
                )
                mute_mins = DEFAULT_FLOOD_MUTE // 60
                mute_label = f"{mute_mins} мин." if mute_mins < 60 else f"{mute_mins // 60} ч."
                warn_msg = await bot_.send_message(
                    chat_id,
                    f"🚫 {user_mention(user.id, user.full_name)} заглушен на {mute_label} за спам "
                    f"(3+ сообщения в секунду).",
                    parse_mode="HTML",
                )
                from utils.helpers import notify_admins
                await notify_admins(
                    bot_,
                    f"🚫 <b>Авто-антиспам</b>\n"
                    f"👤 {user_mention(user.id, user.full_name)} (<code>{user.id}</code>)\n"
                    f"💬 Заглушен на {mute_label} в чате за спам.",
                    source_chat_id=chat_id,
                )
            except Exception:
                pass
            return

        # 4б. Антифлуд (настраиваемый)
        settings = await get_chat_settings(chat_id)
        # Если настроек нет — используем умолчания из config.py
        af_enabled = settings["antiflood_enabled"] if settings else int(DEFAULT_ANTIFLOOD_ENABLED)
        af_limit   = settings["antiflood_limit"]   if settings else DEFAULT_ANTIFLOOD_LIMIT
        if af_enabled and af_limit > 0:
            if check_flood(chat_id, user.id, af_limit, FLOOD_WINDOW):
                try:
                    await event.delete()
                    until = datetime.now() + timedelta(seconds=DEFAULT_FLOOD_MUTE)
                    await bot_.restrict_chat_member(
                        chat_id, user.id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=until,
                    )
                    mute_mins = DEFAULT_FLOOD_MUTE // 60
                    mute_label = f"{mute_mins} мин." if mute_mins < 60 else f"{mute_mins // 60} ч."
                    await bot_.send_message(
                        chat_id,
                        f"⚡ {user_mention(user.id, user.full_name)} заглушен на {mute_label} за флуд.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
                return

        # 5. Замки (locks)
        locks = await get_locks(chat_id)
        if locks:
            reason = None
            if locks["links"] and event.text and _URL_RE.search(event.text):
                reason = "ссылки"
            elif locks["stickers"] and event.sticker:
                reason = "стикеры"
            elif locks["gifs"] and event.animation:
                reason = "гифки"
            elif locks["forwards"] and event.forward_origin:
                reason = "пересылка"
            elif locks["voice"] and event.voice:
                reason = "голосовые"
            elif locks["video"] and event.video_note:
                reason = "кружочки"
            elif locks["photo"] and event.photo:
                reason = "фото"
            elif locks["audio"] and event.audio:
                reason = "аудио"

            if reason:
                try:
                    await event.delete()
                    msg = await bot_.send_message(
                        chat_id,
                        f"🔒 Сообщение удалено — в чате заблокированы: {reason}.",
                    )
                    # Удаляем уведомление через 5 секунд
                    asyncio.create_task(_delete_after(msg))
                except Exception:
                    pass
                return

        # 6. Чёрный список слов
        if event.text:
            settings_bl = settings or await get_chat_settings(chat_id)
            bl_enabled = (
                settings_bl["blacklist_enabled"]
                if settings_bl and settings_bl["blacklist_enabled"] is not None
                else int(DEFAULT_BLACKLIST_ENABLED)
            )
            if bl_enabled:
                blacklist = await get_blacklist(chat_id)
                text_lower = event.text.lower()
                matched = False
                if BLACKLIST_USE_MORPHOLOGY:
                    matched = _check_blacklist_morph(text_lower, blacklist)
                else:
                    for row in blacklist:
                        pattern = r'\b' + re.escape(row["word"]) + r'\b'
                        if re.search(pattern, text_lower):
                            matched = True
                            break
                if matched:
                    try:
                        await event.delete()
                        msg = await bot_.send_message(
                            chat_id,
                            f"⚠️ Сообщение {user_mention(user.id, user.full_name)} удалено "
                            f"(запрещённое слово).",
                            parse_mode="HTML",
                        )
                        asyncio.create_task(_delete_after(msg))
                    except Exception:
                        pass
                    return

        return await handler(event, data)

