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
    add_mora, add_xp_in_chat, apply_pending_import, apply_pending_marriages,
    check_daily_mora, get_blacklist, get_chat_settings, get_filters, get_locks,
    get_todays_quest, get_user_stats, increment_cleanup_count,
    increment_message_count_chat,
    is_group_allowed,
    mark_quest_rewarded, quest_tick,
    set_newbie_shield,
    upsert_chat, upsert_user, upsert_user_stats,
)
from services.recent_users import remember_user
from utils.flood import check_flood
from services.antispam import check_spam
from utils.helpers import user_mention
from utils.ranks import rank_level

# --- pymorphy3 для морфологии чёрного списка ---
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

# Кулдаун моры за сообщения: (user_id, chat_id) -> timestamp последнего дропа
_mora_cooldown: dict[tuple[int, int], float] = {}

# Кэш «первое сообщение за день» для Моры: (user_id, chat_id) -> iso-date
_mora_daily_checked: dict[tuple[int, int], str] = {}

# Трекер юзеров, у которых pending-импорт уже проверен/применён
_pending_resolved: set[tuple[int, int]] = set()   # (user_id, chat_id)
_PENDING_RESOLVED_LIMIT = 5000

# Трекер юзеров, у которых уже проверен щит новичка
_shield_checked: set[tuple[int, int]] = set()     # (user_id, chat_id)
_SHIELD_CHECKED_LIMIT = 10000


async def _delete_after(msg, delay: int = 5) -> None:
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass

_URL_RE = re.compile(
    r"(https?://|www\.|t\.me/|tg://|telegram\.me/)", re.IGNORECASE
)


# Время запуска бота для защиты от старых сообщений
_bot_start_time = None

def set_bot_start_time(start_time: datetime):
    """Установить время запуска бота для защиты от старых сообщений"""
    global _bot_start_time
    _bot_start_time = start_time


def _get_event_antispam_type(event: Message) -> str:
    text = (event.text or event.caption or "").strip().lower()
    if text.startswith("\u0431\u043e\u0442 "):
        return "command"
    return "message"


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
        remember_user(user.id, user.username, user.full_name)

        # Защита от обработки старых сообщений после перезапуска бота
        if _bot_start_time and event.date < _bot_start_time:
            return

        # Возраст сообщения: пакетная доставка после реконнекта не должна мутить
        _msg_age_secs = time.time() - event.date.timestamp()
        _is_stale_msg = _msg_age_secs > 30

        # 0. Белый список групп — разработчик проходит всегда
        _is_admin_group = False
        if event.chat.type in ("group", "supergroup"):
            if not is_group_allowed(event.chat.id) and user.id != DEVELOPER_ID:
                return
            from database.db import get_admin_group_ids
            _is_admin_group = event.chat.id in get_admin_group_ids()

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

            # Pending import
            if user.username:
                _key = (user.id, event.chat.id)
                if _key not in _pending_resolved:
                    _pending_resolved.add(_key)
                    if len(_pending_resolved) > _PENDING_RESOLVED_LIMIT:
                        _pending_resolved.clear()
                    await apply_pending_import(user.username, user.id, event.chat.id)
                    await apply_pending_marriages(user.username, user.id, event.chat.id)

            # Щит новичка: при самом первом сообщении (first_active IS NULL) ставим щит
            _shield_key = (user.id, event.chat.id)
            if _shield_key not in _shield_checked:
                _shield_checked.add(_shield_key)
                if len(_shield_checked) > _SHIELD_CHECKED_LIMIT:
                    _shield_checked.clear()
                _stats_for_shield = await get_user_stats(user.id, event.chat.id)
                if not _stats_for_shield or _stats_for_shield["first_active"] is None:
                    await set_newbie_shield(user.id, event.chat.id, days=3)

            # ПРЯМАЯ запись в БД — каждое сообщение обновляет message_count + last_active
            _msg_count = await increment_message_count_chat(user.id, event.chat.id)
            await increment_cleanup_count(event.chat.id, user.id)
            # Check messages achievements at every 100-message mark (lightweight, idempotent)
            if _msg_count % 100 == 0:
                try:
                    from api.achievements import check_and_award as _ach_check
                    await _ach_check(user.id, event.chat.id, "messages", _msg_count)
                except Exception:
                    pass

            # Чат администрации: только подсчёт сообщений, без моры/XP/квестов
            if _is_admin_group:
                return await handler(event, data)

            # -- Мора: первое сообщение дня (+3) и 7-дневный стрик (+50) --
            from utils.helpers import bot_today as _bot_today
            _today_str = _bot_today()
            _mora_key = (user.id, event.chat.id)
            if len(_mora_daily_checked) > 2000:
                _mora_daily_checked.clear()
            if _mora_daily_checked.get(_mora_key) != _today_str:
                _mora_daily_checked[_mora_key] = _today_str
                is_daily, streak, streak_bonus = await check_daily_mora(user.id, event.chat.id)
                if is_daily:
                    from config import MORA_DAILY_BONUS, MORA_STREAK_BONUS
                    await add_mora(user.id, event.chat.id, MORA_DAILY_BONUS)
                    if streak_bonus:
                        await add_mora(user.id, event.chat.id, MORA_STREAK_BONUS)
                        try:
                            await event.answer(
                                f"\U0001f525 {user_mention(user.id, user.full_name)} \u2014 7-\u0434\u043d\u0435\u0432\u043d\u044b\u0439 \u0441\u0442\u0440\u0438\u043a! "
                                f"<b>+{MORA_STREAK_BONUS} \u041c\u043e\u0440\u044b</b> \U0001fa99",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass

            # -- Мора: шанс получить за сообщение (с кулдауном) --
            from config import (MORA_MSG_CHANCE, MORA_MSG_MIN, MORA_MSG_MAX,
                                MORA_MSG_COOLDOWN, MORA_QUEST_REWARD, MORA_LEVELUP_BONUS)
            from database.db import is_user_single as _is_single
            import random as _mora_rng
            _mora_cd_key = (user.id, event.chat.id)
            _now_mora = time.monotonic()
            if _now_mora - _mora_cooldown.get(_mora_cd_key, 0) >= MORA_MSG_COOLDOWN:
                _single = await _is_single(user.id, event.chat.id)
                _chance  = 0.20          if _single else MORA_MSG_CHANCE
                _min_drop = MORA_MSG_MIN + 1 if _single else MORA_MSG_MIN
                _max_drop = MORA_MSG_MAX + 1 if _single else MORA_MSG_MAX
                if _mora_rng.random() < _chance:
                    _mora_cooldown[_mora_cd_key] = _now_mora
                    _mora_drop = _mora_rng.randint(_min_drop, _max_drop)
                    try:
                        import zoneinfo as _zi
                        _tz_zurich = _zi.ZoneInfo("Europe/Zurich")
                        _now_tz = datetime.now(_tz_zurich)
                        if 0 <= _now_tz.hour < 6:
                            _mora_drop *= 2
                    except Exception:
                        pass
                    await add_mora(user.id, event.chat.id, _mora_drop)

            # Quest progress ("messages" type)
            from utils.helpers import bot_today as _quest_today
            from database.db import get_user_quest as _get_uq
            _today = _quest_today()
            quest = await _get_uq(user.id, event.chat.id, _today)
            if quest["type"] == "messages":
                new_p, goal, just_done = await quest_tick(
                    user.id, event.chat.id, _today, quest["type"], quest["goal"],
                )
                if just_done:
                    _mora_reward = quest.get("mora", MORA_QUEST_REWARD)
                    await add_xp_in_chat(user.id, event.chat.id, quest["xp"])
                    await add_mora(user.id, event.chat.id, _mora_reward)
                    await mark_quest_rewarded(user.id, event.chat.id, _today)
                    try:
                        await event.answer(
                            f"\U0001f389 {user_mention(user.id, user.full_name)} \u0432\u044b\u043f\u043e\u043b\u043d\u0438\u043b \u0435\u0436\u0435\u0434\u043d\u0435\u0432\u043d\u043e\u0435 \u0437\u0430\u0434\u0430\u043d\u0438\u0435! "
                            f"<b>+{quest['xp']} XP</b>  <b>+{_mora_reward} \u041c\u043e\u0440\u044b</b> \U0001fa99",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

            # XP раз в минуту (per-chat)
            now = time.monotonic()
            xp_key = (user.id, event.chat.id)
            if len(_xp_cooldown) > 500:
                cutoff = now - XP_COOLDOWN * 2
                expired = [k for k, v in _xp_cooldown.items() if v <= cutoff]
                for k in expired:
                    del _xp_cooldown[k]
            if now - _xp_cooldown.get(xp_key, 0) >= XP_COOLDOWN:
                _xp_cooldown[xp_key] = now
                from database.db import get_xp_boost_active
                xp_amount = XP_PER_MESSAGE * 2 if await get_xp_boost_active(user.id, event.chat.id) else XP_PER_MESSAGE
                # Block 8: global chat XP buff (+10 %)
                from database.db import get_active_chat_buff as _get_chat_buff
                if await _get_chat_buff(event.chat.id, "xp_plus10"):
                    xp_amount = int(xp_amount * 1.1) or 1
                new_xp, new_level, leveled_up = await add_xp_in_chat(user.id, event.chat.id, xp_amount)
                if leveled_up:
                    await add_mora(user.id, event.chat.id, MORA_LEVELUP_BONUS)
                    # Check level achievements
                    try:
                        from api.achievements import check_and_award as _ach_lvl
                        await _ach_lvl(user.id, event.chat.id, "level", new_level)
                    except Exception:
                        pass
                    if LEVEL_UP_ANNOUNCE:
                        try:
                            await event.answer(
                                f"\U0001f31f {user_mention(user.id, user.full_name)} \u0434\u043e\u0441\u0442\u0438\u0433 <b>{new_level} \u0443\u0440\u043e\u0432\u043d\u044f</b>! "
                                f"(XP: {new_xp}) <b>+{MORA_LEVELUP_BONUS} \u041c\u043e\u0440\u044b</b> \U0001fa99",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass

        # 3. Проверка статуса (все ранги выдаются вручную)
        if in_group:
            key = (event.chat.id, user.id)
            now_mono = time.monotonic()
            if key not in _checked or now_mono - _checked[key] > _CHECKED_TTL:
                _checked[key] = now_mono
                if len(_checked) > 1000:
                    cutoff = now_mono - _CHECKED_TTL
                    expired = [k for k, v in _checked.items() if v <= cutoff]
                    for k in expired:
                        del _checked[k]

        # Авто-мод только в группах
        if not in_group:
            return await handler(event, data)

        # Разработчик всегда проходит авто-мод
        if DEVELOPER_ID and user.id == DEVELOPER_ID:
            return await handler(event, data)

        stats = await get_user_stats(user.id, event.chat.id)
        user_rank = stats["rank"] if stats else "user"

        # Модераторы и выше освобождены от авто-мода
        if rank_level(user_rank) >= rank_level("moderator"):
            return await handler(event, data)

        bot_: Bot = data["bot"]
        chat_id = event.chat.id

        # 4а. Авто-детект спама: Token Bucket (всегда включён)
        if check_spam(user.id, chat_id, _get_event_antispam_type(event)):
            if not _is_stale_msg:
                try:
                    await event.delete()
                    until = datetime.now() + timedelta(seconds=DEFAULT_FLOOD_MUTE)
                    await bot_.restrict_chat_member(
                        chat_id, user.id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=until,
                    )
                    mute_mins = DEFAULT_FLOOD_MUTE // 60
                    mute_label = f"{mute_mins} \u043c\u0438\u043d." if mute_mins < 60 else f"{mute_mins // 60} \u0447."
                    await bot_.send_message(
                        chat_id,
                        f"\U0001f6ab {user_mention(user.id, user.full_name)} \u0437\u0430\u0433\u043b\u0443\u0448\u0435\u043d \u043d\u0430 {mute_label} \u0437\u0430 \u0441\u043f\u0430\u043c.",
                        parse_mode="HTML",
                    )
                    from utils.helpers import notify_admins
                    await notify_admins(
                        bot_,
                        f"\U0001f6ab <b>\u0410\u0432\u0442\u043e-\u0430\u043d\u0442\u0438\u0441\u043f\u0430\u043c</b>\n"
                        f"\U0001f464 {user_mention(user.id, user.full_name)} (<code>{user.id}</code>)\n"
                        f"\U0001f4ac \u0417\u0430\u0433\u043b\u0443\u0448\u0435\u043d \u043d\u0430 {mute_label} \u0432 \u0447\u0430\u0442\u0435 \u0437\u0430 \u0441\u043f\u0430\u043c.",
                        source_chat_id=chat_id,
                    )
                except Exception:
                    pass
            return

        # 4б. Антифлуд (настраиваемый)
        settings = await get_chat_settings(chat_id)

        # Блокировка сообщений во время чистки
        if settings and settings.get("cleanup_locked"):
            try:
                await event.delete()
            except Exception:
                pass
            return

        af_enabled = settings["antiflood_enabled"] if settings else int(DEFAULT_ANTIFLOOD_ENABLED)
        af_limit   = settings["antiflood_limit"]   if settings else DEFAULT_ANTIFLOOD_LIMIT
        af_window  = (settings["antiflood_window"] if settings and settings["antiflood_window"] else None) or FLOOD_WINDOW
        if af_enabled and af_limit > 0:
            if check_flood(chat_id, user.id, af_limit, af_window):
                try:
                    await event.delete()
                    until = datetime.now() + timedelta(seconds=DEFAULT_FLOOD_MUTE)
                    await bot_.restrict_chat_member(
                        chat_id, user.id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=until,
                    )
                    mute_mins = DEFAULT_FLOOD_MUTE // 60
                    mute_label = f"{mute_mins} \u043c\u0438\u043d." if mute_mins < 60 else f"{mute_mins // 60} \u0447."
                    await bot_.send_message(
                        chat_id,
                        f"\u26a1 {user_mention(user.id, user.full_name)} \u0437\u0430\u0433\u043b\u0443\u0448\u0435\u043d \u043d\u0430 {mute_label} \u0437\u0430 \u0444\u043b\u0443\u0434.",
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
                reason = "\u0441\u0441\u044b\u043b\u043a\u0438"
            elif locks["stickers"] and event.sticker:
                reason = "\u0441\u0442\u0438\u043a\u0435\u0440\u044b"
            elif locks["gifs"] and event.animation:
                reason = "\u0433\u0438\u0444\u043a\u0438"
            elif locks["forwards"] and event.forward_origin:
                reason = "\u043f\u0435\u0440\u0435\u0441\u044b\u043b\u043a\u0430"
            elif locks["voice"] and event.voice:
                reason = "\u0433\u043e\u043b\u043e\u0441\u043e\u0432\u044b\u0435"
            elif locks["video"] and event.video_note:
                reason = "\u043a\u0440\u0443\u0436\u043e\u0447\u043a\u0438"
            elif locks["photo"] and event.photo:
                reason = "\u0444\u043e\u0442\u043e"
            elif locks["audio"] and event.audio:
                reason = "\u0430\u0443\u0434\u0438\u043e"

            if reason:
                try:
                    await event.delete()
                    msg = await bot_.send_message(
                        chat_id,
                        f"\U0001f512 \u0421\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u0443\u0434\u0430\u043b\u0435\u043d\u043e \u2014 \u0432 \u0447\u0430\u0442\u0435 \u0437\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d\u044b: {reason}.",
                    )
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
                            f"\u26a0\ufe0f \u0421\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 {user_mention(user.id, user.full_name)} \u0443\u0434\u0430\u043b\u0435\u043d\u043e "
                            f"(\u0437\u0430\u043f\u0440\u0435\u0449\u0451\u043d\u043d\u043e\u0435 \u0441\u043b\u043e\u0432\u043e).",
                            parse_mode="HTML",
                        )
                        asyncio.create_task(_delete_after(msg))
                    except Exception:
                        pass
                    return

        return await handler(event, data)
