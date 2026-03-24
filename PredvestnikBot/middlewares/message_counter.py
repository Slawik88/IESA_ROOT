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
    increment_message_count_chat, is_group_allowed,
    mark_quest_rewarded, quest_tick,
    upsert_chat, upsert_user, upsert_user_stats,
)
from utils.flood import check_flood, check_spam
from utils.helpers import user_mention
from utils.ranks import rank_level

# в”Ђв”Ђв”Ђ pymorphy3 РґР»СЏ РјРѕСЂС„РѕР»РѕРіРёРё С‡С‘СЂРЅРѕРіРѕ СЃРїРёСЃРєР° в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
_morph = None
_word_re = re.compile(r'[Р°-СЏС‘a-z0-9]+', re.IGNORECASE)

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

# РљСЌС€: (chat_id, user_id) -> timestamp РїРѕСЃР»РµРґРЅРµР№ РїСЂРѕРІРµСЂРєРё СЃС‚Р°С‚СѓСЃР°
_checked: dict[tuple[int, int], float] = {}
_CHECKED_TTL = 3600.0  # РїРµСЂРµРїСЂРѕРІРµСЂСЏС‚СЊ СЂР°Р· РІ С‡Р°СЃ

# РљСѓР»РґР°СѓРЅ XP: (user_id, chat_id) -> timestamp РїРѕСЃР»РµРґРЅРµРіРѕ РЅР°С‡РёСЃР»РµРЅРёСЏ
_xp_cooldown: dict[tuple[int, int], float] = {}

# РљСѓР»РґР°СѓРЅ РјРѕСЂС‹ Р·Р° СЃРѕРѕР±С‰РµРЅРёСЏ: (user_id, chat_id) -> timestamp РїРѕСЃР»РµРґРЅРµРіРѕ РґСЂРѕРїР°
_mora_cooldown: dict[tuple[int, int], float] = {}

# РљСЌС€ В«РїРµСЂРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ Р·Р° РґРµРЅСЊВ» РґР»СЏ РњРѕСЂС‹: (user_id, chat_id) -> iso-date
_mora_daily_checked: dict[tuple[int, int], str] = {}

# РўСЂРµРєРµСЂ СЋР·РµСЂРѕРІ, Сѓ РєРѕС‚РѕСЂС‹С… pending-РёРјРїРѕСЂС‚ СѓР¶Рµ РїСЂРѕРІРµСЂРµРЅ/РїСЂРёРјРµРЅС‘РЅ
_pending_resolved: set[tuple[int, int]] = set()   # (user_id, chat_id)
_PENDING_RESOLVED_LIMIT = 5000


async def _delete_after(msg, delay: int = 5) -> None:
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass

_URL_RE = re.compile(
    r"(https?://|www\.|t\.me/|tg://|telegram\.me/)", re.IGNORECASE
)


# Р’СЂРµРјСЏ Р·Р°РїСѓСЃРєР° Р±РѕС‚Р° РґР»СЏ Р·Р°С‰РёС‚С‹ РѕС‚ СЃС‚Р°СЂС‹С… СЃРѕРѕР±С‰РµРЅРёР№
_bot_start_time = None

def set_bot_start_time(start_time: datetime):
    """РЈСЃС‚Р°РЅРѕРІРёС‚СЊ РІСЂРµРјСЏ Р·Р°РїСѓСЃРєР° Р±РѕС‚Р° РґР»СЏ Р·Р°С‰РёС‚С‹ РѕС‚ СЃС‚Р°СЂС‹С… СЃРѕРѕР±С‰РµРЅРёР№"""
    global _bot_start_time
    _bot_start_time = start_time


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

        # рџ›ЎпёЏ Р—Р°С‰РёС‚Р° РѕС‚ РѕР±СЂР°Р±РѕС‚РєРё СЃС‚Р°СЂС‹С… СЃРѕРѕР±С‰РµРЅРёР№ РїРѕСЃР»Рµ РїРµСЂРµР·Р°РїСѓСЃРєР° Р±РѕС‚Р°
        # (РїСЂРµРґРѕС‚РІСЂР°С‰Р°РµС‚ РјСѓС‚С‹/РєРёРєРё Р·Р° СЃРѕРѕР±С‰РµРЅРёСЏ, РѕС‚РїСЂР°РІР»РµРЅРЅС‹Рµ РїРѕРєР° Р±РѕС‚ Р±С‹Р» РЅРµР°РєС‚РёРІРµРЅ)
        if _bot_start_time and event.date < _bot_start_time:
            # РРіРЅРѕСЂРёСЂСѓРµРј СЃРѕРѕР±С‰РµРЅРёСЏ, РѕС‚РїСЂР°РІР»РµРЅРЅС‹Рµ РґРѕ Р·Р°РїСѓСЃРєР° Р±РѕС‚Р°
            return

        # 0. Р‘РµР»С‹Р№ СЃРїРёСЃРѕРє РіСЂСѓРїРї вЂ” РµСЃР»Рё РІРєР»СЋС‡С‘РЅ, РёРіРЅРѕСЂРёСЂСѓРµРј РЅРµСЂР°Р·СЂРµС€С‘РЅРЅС‹Рµ РіСЂСѓРїРїС‹
        #    (СЂР°Р·СЂР°Р±РѕС‚С‡РёРє РІСЃРµРіРґР° РїСЂРѕС…РѕРґРёС‚, С‡С‚РѕР±С‹ РјРѕРі РґРѕР±Р°РІРёС‚СЊ РіСЂСѓРїРїСѓ)
        if event.chat.type in ("group", "supergroup"):
            if not is_group_allowed(event.chat.id) and user.id != DEVELOPER_ID:
                return
            # РђРґРјРёРЅ-РіСЂСѓРїРїС‹ вЂ” С‚РѕР»СЊРєРѕ РґР»СЏ СЃРёСЃС‚РµРјРЅС‹С… СѓРІРµРґРѕРјР»РµРЅРёР№, Р±РµР· СЃС‚Р°С‚РёСЃС‚РёРєРё/Р°РІС‚Рѕ-РјРѕРґР°
            from database.db import get_admin_group_ids
            if event.chat.id in get_admin_group_ids():
                return await handler(event, data)

        # 1. Р РµРіРёСЃС‚СЂР°С†РёСЏ / РѕР±РЅРѕРІР»РµРЅРёРµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
        await upsert_user(user.id, user.username or "", user.full_name or "")

        await upsert_chat(
            event.chat.id,
            getattr(event.chat, "title", "") or getattr(event.chat, "full_name", ""),
            getattr(event.chat, "username", "") or "",
            event.chat.type,
            1,
        )

        in_group = event.chat.type in ("group", "supergroup")

        # 2. Per-chat profile + РїРѕРґСЃС‡С‘С‚ СЃРѕРѕР±С‰РµРЅРёР№ (С‚РѕР»СЊРєРѕ РІ РіСЂСѓРїРїР°С…)
        if in_group:
            await upsert_user_stats(user.id, event.chat.id)

            # Pending import: РїСЂРёРјРµРЅСЏРµРј РѕРґРёРЅ СЂР°Р· РїСЂРё РїРµСЂРІРѕРј СЃРѕРѕР±С‰РµРЅРёРё СЋР·РµСЂР° РІ СЌС‚РѕРј С‡Р°С‚Рµ
            if user.username:
                _key = (user.id, event.chat.id)
                if _key not in _pending_resolved:
                    _pending_resolved.add(_key)
                    if len(_pending_resolved) > _PENDING_RESOLVED_LIMIT:
                        _pending_resolved.clear()
                    await apply_pending_import(user.username, user.id, event.chat.id)
                    await apply_pending_marriages(user.username, user.id, event.chat.id)

            msg_count = await increment_message_count_chat(user.id, event.chat.id)
            await increment_cleanup_count(event.chat.id, user.id)

            # в”Ђв”Ђ РњРѕСЂР°: РїРµСЂРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ РґРЅСЏ (+3) Рё 7-РґРЅРµРІРЅС‹Р№ СЃС‚СЂРёРє (+50) в”Ђв”Ђ
            from utils.helpers import bot_today as _bot_today
            _today_str = _bot_today()
            _mora_key = (user.id, event.chat.id)
            # РџРµСЂРёРѕРґРёС‡РµСЃРєР°СЏ РѕС‡РёСЃС‚РєР° РєСЌС€Р° РµР¶РµРґРЅРµРІРЅРѕР№ РїСЂРѕРІРµСЂРєРё
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
                                f"рџ”Ґ {user_mention(user.id, user.full_name)} вЂ” 7-РґРЅРµРІРЅС‹Р№ СЃС‚СЂРёРє! "
                                f"<b>+{MORA_STREAK_BONUS} РњРѕСЂС‹</b> рџЄ™",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass

            # в”Ђв”Ђ РњРѕСЂР°: С€Р°РЅСЃ РїРѕР»СѓС‡РёС‚СЊ Р·Р° СЃРѕРѕР±С‰РµРЅРёРµ (СЃ РєСѓР»РґР°СѓРЅРѕРј) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
            from config import (MORA_MSG_CHANCE, MORA_MSG_MIN, MORA_MSG_MAX,
                                MORA_MSG_COOLDOWN, MORA_QUEST_REWARD, MORA_LEVELUP_BONUS)
            from database.db import is_user_single as _is_single
            import random as _mora_rng
            _mora_cd_key = (user.id, event.chat.id)
            _now_mora = time.monotonic()
            if _now_mora - _mora_cooldown.get(_mora_cd_key, 0) >= MORA_MSG_COOLDOWN:
                # РџРµСЂРє РѕРґРёРЅРѕС‡РєРё: 20% С€Р°РЅСЃ, 2-4 РњРѕСЂС‹ (vs 17% Рё 1-3 РґР»СЏ РїР°СЂ)
                _single = await _is_single(user.id, event.chat.id)
                _chance  = 0.20          if _single else MORA_MSG_CHANCE  # 20% vs 17%
                _min_drop = MORA_MSG_MIN + 1 if _single else MORA_MSG_MIN  # 2 vs 1
                _max_drop = MORA_MSG_MAX + 1 if _single else MORA_MSG_MAX  # 4 vs 3
                if _mora_rng.random() < _chance:
                    _mora_cooldown[_mora_cd_key] = _now_mora
                    _mora_drop = _mora_rng.randint(_min_drop, _max_drop)
                    # РќРѕС‡РЅР°СЏ СЃРјРµРЅР° 00:00вЂ“06:00 (Europe/Zurich) в†’ x2 РњРѕСЂР°
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
                            f"рџЋ‰ {user_mention(user.id, user.full_name)} РІС‹РїРѕР»РЅРёР» РµР¶РµРґРЅРµРІРЅРѕРµ Р·Р°РґР°РЅРёРµ! "
                            f"<b>+{quest['xp']} XP</b>  <b>+{_mora_reward} РњРѕСЂС‹</b> рџЄ™",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

            # XP СЂР°Р· РІ РјРёРЅСѓС‚Сѓ (per-chat)
            now = time.monotonic()
            # РћС‡РёС‰Р°РµРј РїСЂРѕСЃСЂРѕС‡РµРЅРЅС‹Рµ Р·Р°РїРёСЃРё (РІС‹Р±РѕСЂРѕС‡РЅРѕ, РЅРµ РїРѕР»РЅР°СЏ РѕС‡РёСЃС‚РєР°)
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
                new_xp, new_level, leveled_up = await add_xp_in_chat(user.id, event.chat.id, xp_amount)
                if leveled_up:
                    await add_mora(user.id, event.chat.id, MORA_LEVELUP_BONUS)
                    if LEVEL_UP_ANNOUNCE:
                        try:
                            await event.answer(
                                f"рџЊџ {user_mention(user.id, user.full_name)} РґРѕСЃС‚РёРі <b>{new_level} СѓСЂРѕРІРЅСЏ</b>! "
                                f"(XP: {new_xp}) <b>+{MORA_LEVELUP_BONUS} РњРѕСЂС‹</b> рџЄ™",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass

        # 3. РџСЂРѕРІРµСЂРєР° СЃС‚Р°С‚СѓСЃР° РІС‹РїРѕР»РЅСЏРµС‚СЃСЏ Р±РµР· Р°РІС‚Рѕ-РїРѕРІС‹С€РµРЅРёР№ (РІСЃРµ СЂР°РЅРіРё РІС‹РґР°СЋС‚СЃСЏ РІСЂСѓС‡РЅСѓСЋ)
        if in_group:
            key = (event.chat.id, user.id)
            now_mono = time.monotonic()
            if key not in _checked or now_mono - _checked[key] > _CHECKED_TTL:
                _checked[key] = now_mono
                # РџРµСЂРёРѕРґРёС‡РµСЃРєР°СЏ РѕС‡РёСЃС‚РєР° СѓСЃС‚Р°СЂРµРІС€РёС… Р·Р°РїРёСЃРµР№
                if len(_checked) > 1000:
                    cutoff = now_mono - _CHECKED_TTL
                    expired = [k for k, v in _checked.items() if v <= cutoff]
                    for k in expired:
                        del _checked[k]

        # РђРІС‚Рѕ-РјРѕРґ С‚РѕР»СЊРєРѕ РІ РіСЂСѓРїРїР°С…
        if not in_group:
            return await handler(event, data)

        # Р Р°Р·СЂР°Р±РѕС‚С‡РёРє РІСЃРµРіРґР° РїСЂРѕС…РѕРґРёС‚ Р°РІС‚Рѕ-РјРѕРґ РЅРµР·Р°РІРёСЃРёРјРѕ РѕС‚ СЃРѕСЃС‚РѕСЏРЅРёСЏ Р‘Р”
        if DEVELOPER_ID and user.id == DEVELOPER_ID:
            return await handler(event, data)

        stats = await get_user_stats(user.id, event.chat.id)
        user_rank = stats["rank"] if stats else "user"

        # РњРѕРґРµСЂР°С‚РѕСЂС‹ Рё РІС‹С€Рµ РѕСЃРІРѕР±РѕР¶РґРµРЅС‹ РѕС‚ Р°РІС‚Рѕ-РјРѕРґР°
        if rank_level(user_rank) >= rank_level("moderator"):
            return await handler(event, data)

        bot_: Bot = data["bot"]
        chat_id = event.chat.id

        # 4Р°. РђРІС‚Рѕ-РґРµС‚РµРєС‚ СЃРїР°РјР°: > 3 СЃРѕРѕР±С‰РµРЅРёР№ Р·Р° 1 СЃРµРєСѓРЅРґСѓ в†’ РјСѓС‚ 5 РјРёРЅСѓС‚ (РІСЃРµРіРґР° РІРєР»СЋС‡С‘РЅ)
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
                mute_label = f"{mute_mins} РјРёРЅ." if mute_mins < 60 else f"{mute_mins // 60} С‡."
                warn_msg = await bot_.send_message(
                    chat_id,
                    f"рџљ« {user_mention(user.id, user.full_name)} Р·Р°РіР»СѓС€РµРЅ РЅР° {mute_label} Р·Р° СЃРїР°Рј "
                    f"(3+ СЃРѕРѕР±С‰РµРЅРёСЏ РІ СЃРµРєСѓРЅРґСѓ).",
                    parse_mode="HTML",
                )
                from utils.helpers import notify_admins
                await notify_admins(
                    bot_,
                    f"рџљ« <b>РђРІС‚Рѕ-Р°РЅС‚РёСЃРїР°Рј</b>\n"
                    f"рџ‘¤ {user_mention(user.id, user.full_name)} (<code>{user.id}</code>)\n"
                    f"рџ’¬ Р—Р°РіР»СѓС€РµРЅ РЅР° {mute_label} РІ С‡Р°С‚Рµ Р·Р° СЃРїР°Рј.",
                    source_chat_id=chat_id,
                )
            except Exception:
                pass
            return

        # 4Р±. РђРЅС‚РёС„Р»СѓРґ (РЅР°СЃС‚СЂР°РёРІР°РµРјС‹Р№)
        settings = await get_chat_settings(chat_id)

        # Р‘Р»РѕРєРёСЂРѕРІРєР° СЃРѕРѕР±С‰РµРЅРёР№ РІРѕ РІСЂРµРјСЏ С‡РёСЃС‚РєРё (РґР»СЏ rank < moderator)
        if settings and settings.get("cleanup_locked"):
            try:
                await event.delete()
            except Exception:
                pass
            return

        # Р•СЃР»Рё РЅР°СЃС‚СЂРѕРµРє РЅРµС‚ вЂ” РёСЃРїРѕР»СЊР·СѓРµРј СѓРјРѕР»С‡Р°РЅРёСЏ РёР· config.py
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
                    mute_label = f"{mute_mins} РјРёРЅ." if mute_mins < 60 else f"{mute_mins // 60} С‡."
                    await bot_.send_message(
                        chat_id,
                        f"вљЎ {user_mention(user.id, user.full_name)} Р·Р°РіР»СѓС€РµРЅ РЅР° {mute_label} Р·Р° С„Р»СѓРґ.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
                return

        # 5. Р—Р°РјРєРё (locks)
        locks = await get_locks(chat_id)
        if locks:
            reason = None
            if locks["links"] and event.text and _URL_RE.search(event.text):
                reason = "СЃСЃС‹Р»РєРё"
            elif locks["stickers"] and event.sticker:
                reason = "СЃС‚РёРєРµСЂС‹"
            elif locks["gifs"] and event.animation:
                reason = "РіРёС„РєРё"
            elif locks["forwards"] and event.forward_origin:
                reason = "РїРµСЂРµСЃС‹Р»РєР°"
            elif locks["voice"] and event.voice:
                reason = "РіРѕР»РѕСЃРѕРІС‹Рµ"
            elif locks["video"] and event.video_note:
                reason = "РєСЂСѓР¶РѕС‡РєРё"
            elif locks["photo"] and event.photo:
                reason = "С„РѕС‚Рѕ"
            elif locks["audio"] and event.audio:
                reason = "Р°СѓРґРёРѕ"

            if reason:
                try:
                    await event.delete()
                    msg = await bot_.send_message(
                        chat_id,
                        f"рџ”’ РЎРѕРѕР±С‰РµРЅРёРµ СѓРґР°Р»РµРЅРѕ вЂ” РІ С‡Р°С‚Рµ Р·Р°Р±Р»РѕРєРёСЂРѕРІР°РЅС‹: {reason}.",
                    )
                    # РЈРґР°Р»СЏРµРј СѓРІРµРґРѕРјР»РµРЅРёРµ С‡РµСЂРµР· 5 СЃРµРєСѓРЅРґ
                    asyncio.create_task(_delete_after(msg))
                except Exception:
                    pass
                return

        # 6. Р§С‘СЂРЅС‹Р№ СЃРїРёСЃРѕРє СЃР»РѕРІ
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
                            f"вљ пёЏ РЎРѕРѕР±С‰РµРЅРёРµ {user_mention(user.id, user.full_name)} СѓРґР°Р»РµРЅРѕ "
                            f"(Р·Р°РїСЂРµС‰С‘РЅРЅРѕРµ СЃР»РѕРІРѕ).",
                            parse_mode="HTML",
                        )
                        asyncio.create_task(_delete_after(msg))
                    except Exception:
                        pass
                    return

        return await handler(event, data)

