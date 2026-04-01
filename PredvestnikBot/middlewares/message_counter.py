"""
middlewares/message_counter.py вЂ” AutoModMiddleware

Per-message pipeline for every incoming group/DM message:
  1. Guard: skip bots and stale messages (before bot restart)
  2. Detect chat isolation (admin group / test chat)
  3. Register user + chat in DB
  4. Early-return for isolated chats вЂ” economy fully blocked
     (add_mora / add_xp_in_chat also guard at DB level as a safety net)
  5. Group economy: message count, Mora, XP, quests, achievements
  6. Automod: antispam в†’ antiflood в†’ locks в†’ blacklist
"""

import asyncio
import random
import re
import time
import zoneinfo
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot
from aiogram.types import ChatPermissions, Message

from config import (
    DEFAULT_ANTIFLOOD_ENABLED, DEFAULT_ANTIFLOOD_LIMIT,
    DEFAULT_BLACKLIST_ENABLED, DEFAULT_FLOOD_MUTE, DEVELOPER_ID, FLOOD_WINDOW,
    LEVEL_UP_ANNOUNCE, XP_COOLDOWN, XP_PER_MESSAGE, BLACKLIST_USE_MORPHOLOGY,
    MORA_DAILY_BONUS, MORA_LEVELUP_BONUS, MORA_MSG_CHANCE, MORA_MSG_COOLDOWN,
    MORA_MSG_MAX, MORA_MSG_MIN, MORA_QUEST_REWARD, MORA_STREAK_BONUS,
)
from database.db import (
    add_mora, add_xp_in_chat,
    apply_pending_import, apply_pending_marriages,
    check_daily_mora,
    get_active_chat_buff, get_blacklist, get_chat_settings, get_locks,
    get_user_quest, get_user_stats, get_xp_boost_active,
    increment_cleanup_count, increment_message_count_chat,
    is_user_single, mark_quest_rewarded, quest_tick, set_newbie_shield,
    upsert_chat, upsert_user, upsert_user_stats,
    get_admin_group_ids, is_test_chat,
)
from services.antispam import check_spam
from services.recent_users import remember_user
from utils.flood import check_flood
from utils.helpers import bot_today, notify_admins, user_mention
from utils.ranks import rank_level

# в”Ђв”Ђв”Ђ Constants в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
_TZ_ZURICH = zoneinfo.ZoneInfo("Europe/Zurich")
_URL_RE = re.compile(r"(https?://|www\.|t\.me/|tg://|telegram\.me/)", re.IGNORECASE)
_WORD_RE = re.compile(r"[Р°-СЏС‘a-z0-9]+", re.IGNORECASE)

# в”Ђв”Ђв”Ђ In-memory caches в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
_checked:            dict[tuple[int, int], float] = {}   # (chat_id, user_id) в†’ last_check ts
_xp_cooldown:        dict[tuple[int, int], float] = {}   # (user_id, chat_id) в†’ last_xp ts
_mora_cooldown:      dict[tuple[int, int], float] = {}   # (user_id, chat_id) в†’ last_drop ts
_mora_daily_checked: dict[tuple[int, int], str]   = {}   # (user_id, chat_id) в†’ iso-date
_pending_resolved:   set[tuple[int, int]]          = set()
_shield_checked:     set[tuple[int, int]]          = set()

_CHECKED_TTL             = 3600.0
_PENDING_RESOLVED_LIMIT  = 5_000
_SHIELD_CHECKED_LIMIT    = 10_000

# в”Ђв”Ђв”Ђ Bot start-time guard в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
_bot_start_time: datetime | None = None

def set_bot_start_time(start_time: datetime) -> None:
    global _bot_start_time
    _bot_start_time = start_time

# в”Ђв”Ђв”Ђ pymorphy3 (lazy init) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
_morph = None

def _get_morph():
    global _morph
    if _morph is None:
        import pymorphy3
        _morph = pymorphy3.MorphAnalyzer()
    return _morph

def _lemmatize(word: str) -> str:
    return _get_morph().parse(word)[0].normal_form

def _check_blacklist_morph(text_lower: str, blacklist) -> bool:
    lemmas = {_lemmatize(w) for w in _WORD_RE.findall(text_lower)}
    return any(_lemmatize(row["word"].lower()) in lemmas for row in blacklist)

# в”Ђв”Ђв”Ђ Helpers в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

async def _delete_after(msg, delay: int = 5) -> None:
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass


def _antispam_type(event: Message) -> str:
    text = (event.text or event.caption or "").strip().lower()
    return "command" if text.startswith("Р±РѕС‚ ") else "message"


async def _process_economy(user_id: int, chat_id: int, event: Message) -> None:
    """Award daily Mora, random Mora drop, and advance message-type quest."""
    today = bot_today()
    key = (user_id, chat_id)

    # Daily bonus + 7-day streak
    if len(_mora_daily_checked) > 2_000:
        _mora_daily_checked.clear()
    if _mora_daily_checked.get(key) != today:
        _mora_daily_checked[key] = today
        is_daily, _streak, streak_bonus = await check_daily_mora(user_id, chat_id)
        if is_daily:
            await add_mora(user_id, chat_id, MORA_DAILY_BONUS)
            if streak_bonus:
                await add_mora(user_id, chat_id, MORA_STREAK_BONUS)
                try:
                    await event.answer(
                        f"рџ”Ґ {user_mention(user_id, event.from_user.full_name)}"
                        f" вЂ” 7-РґРЅРµРІРЅС‹Р№ СЃС‚СЂРёРє! <b>+{MORA_STREAK_BONUS} РњРѕСЂС‹</b> рџЄ™",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

    # Random Mora drop (with per-user cooldown)
    now = time.monotonic()
    if now - _mora_cooldown.get(key, 0) >= MORA_MSG_COOLDOWN:
        single   = await is_user_single(user_id, chat_id)
        chance   = 0.20 if single else MORA_MSG_CHANCE
        min_drop = MORA_MSG_MIN + (1 if single else 0)
        max_drop = MORA_MSG_MAX + (1 if single else 0)
        if random.random() < chance:
            _mora_cooldown[key] = now
            drop = random.randint(min_drop, max_drop)
            if 0 <= datetime.now(_TZ_ZURICH).hour < 6:
                drop *= 2  # night bonus
            await add_mora(user_id, chat_id, drop)

    # Message-type quest progress
    quest = await get_user_quest(user_id, chat_id, today)
    if quest["type"] == "messages":
        _new_p, _goal, just_done = await quest_tick(
            user_id, chat_id, today, quest["type"], quest["goal"],
        )
        if just_done:
            mora_reward = quest.get("mora", MORA_QUEST_REWARD)
            await add_xp_in_chat(user_id, chat_id, quest["xp"])
            await add_mora(user_id, chat_id, mora_reward)
            await mark_quest_rewarded(user_id, chat_id, today)
            try:
                await event.answer(
                    f"рџЋ‰ {user_mention(user_id, event.from_user.full_name)}"
                    f" РІС‹РїРѕР»РЅРёР» РµР¶РµРґРЅРµРІРЅРѕРµ Р·Р°РґР°РЅРёРµ!"
                    f" <b>+{quest['xp']} XP</b>  <b>+{mora_reward} РњРѕСЂС‹</b> рџЄ™",
                    parse_mode="HTML",
                )
            except Exception:
                pass


async def _process_xp(user_id: int, chat_id: int, event: Message) -> None:
    """Award per-message XP (once per cooldown). Announce level-ups."""
    now = time.monotonic()
    key = (user_id, chat_id)

    # Prune stale cooldown entries
    if len(_xp_cooldown) > 500:
        cutoff = now - XP_COOLDOWN * 2
        stale = [k for k, v in _xp_cooldown.items() if v <= cutoff]
        for k in stale:
            del _xp_cooldown[k]

    if now - _xp_cooldown.get(key, 0) < XP_COOLDOWN:
        return
    _xp_cooldown[key] = now

    xp = XP_PER_MESSAGE * 2 if await get_xp_boost_active(user_id, chat_id) else XP_PER_MESSAGE
    if await get_active_chat_buff(chat_id, "xp_plus10"):
        xp = max(1, int(xp * 1.1))

    new_xp, new_level, leveled_up = await add_xp_in_chat(user_id, chat_id, xp)
    if leveled_up:
        await add_mora(user_id, chat_id, MORA_LEVELUP_BONUS)
        try:
            from api.achievements import check_and_award as _ach
            await _ach(user_id, chat_id, "level", new_level)
        except Exception:
            pass
        if LEVEL_UP_ANNOUNCE:
            try:
                await event.answer(
                    f"рџЊџ {user_mention(user_id, event.from_user.full_name)}"
                    f" РґРѕСЃС‚РёРі <b>{new_level} СѓСЂРѕРІРЅСЏ</b>!"
                    f" (XP: {new_xp}) <b>+{MORA_LEVELUP_BONUS} РњРѕСЂС‹</b> рџЄ™",
                    parse_mode="HTML",
                )
            except Exception:
                pass


# в”Ђв”Ђв”Ђ Middleware в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

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

        # в”Ђв”Ђ Guard: skip messages from before bot restart в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
        if _bot_start_time and event.date < _bot_start_time:
            return

        is_stale = (time.time() - event.date.timestamp()) > 30
        in_group = event.chat.type in ("group", "supergroup")

        # в”Ђв”Ђ Detect isolation (admin group / test chat) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
        is_isolated = in_group and (
            event.chat.id in get_admin_group_ids() or is_test_chat(event.chat.id)
        )
        data["is_isolated_chat"] = is_isolated

        # в”Ђв”Ђ Always register user + chat в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
        await upsert_user(user.id, user.username or "", user.full_name or "")
        await upsert_chat(
            event.chat.id,
            getattr(event.chat, "title", "") or getattr(event.chat, "full_name", ""),
            getattr(event.chat, "username", "") or "",
            event.chat.type,
            1,
        )

        # в”Ђв”Ђ Isolated chats: skip economy, pass to handler в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
        # DB-level guards in add_mora/add_xp_in_chat act as an additional
        # safety net in case any code path bypasses this early return.
        if is_isolated:
            return await handler(event, data)

        # в”Ђв”Ђ Group economy (non-isolated groups only) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
        if in_group:
            await upsert_user_stats(user.id, event.chat.id)

            # Resolve pending username imports + marriages (once per session)
            if user.username:
                p_key = (user.id, event.chat.id)
                if p_key not in _pending_resolved:
                    _pending_resolved.add(p_key)
                    if len(_pending_resolved) > _PENDING_RESOLVED_LIMIT:
                        _pending_resolved.clear()
                    await apply_pending_import(user.username, user.id, event.chat.id)
                    await apply_pending_marriages(user.username, user.id, event.chat.id)

            # Newbie shield on first message ever
            s_key = (user.id, event.chat.id)
            if s_key not in _shield_checked:
                _shield_checked.add(s_key)
                if len(_shield_checked) > _SHIELD_CHECKED_LIMIT:
                    _shield_checked.clear()
                stats = await get_user_stats(user.id, event.chat.id)
                if not stats or stats["first_active"] is None:
                    await set_newbie_shield(user.id, event.chat.id, days=3)

            # Message count (every message)
            msg_count = await increment_message_count_chat(user.id, event.chat.id)
            await increment_cleanup_count(event.chat.id, user.id)
            if msg_count % 100 == 0:
                try:
                    from api.achievements import check_and_award as _ach
                    await _ach(user.id, event.chat.id, "messages", msg_count)
                except Exception:
                    pass

            # Mora + quests
            await _process_economy(user.id, event.chat.id, event)

            # XP + level-up
            await _process_xp(user.id, event.chat.id, event)

        # в”Ђв”Ђ Automod (groups only) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
        if not in_group:
            return await handler(event, data)

        if DEVELOPER_ID and user.id == DEVELOPER_ID:
            return await handler(event, data)

        stats = await get_user_stats(user.id, event.chat.id)
        user_rank = (stats["rank"] if stats else None) or "user"
        if rank_level(user_rank) >= rank_level("moderator"):
            return await handler(event, data)

        bot_: Bot = data["bot"]
        chat_id = event.chat.id

        # Antispam вЂ” Token Bucket (always enabled)
        if check_spam(user.id, chat_id, _antispam_type(event)):
            if not is_stale:
                try:
                    await event.delete()
                    until = datetime.now() + timedelta(seconds=DEFAULT_FLOOD_MUTE)
                    await bot_.restrict_chat_member(
                        chat_id, user.id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=until,
                    )
                    mins = DEFAULT_FLOOD_MUTE // 60
                    label = f"{mins} РјРёРЅ." if mins < 60 else f"{mins // 60} С‡."
                    await bot_.send_message(
                        chat_id,
                        f"рџљ« {user_mention(user.id, user.full_name)}"
                        f" Р·Р°РіР»СѓС€РµРЅ РЅР° {label} Р·Р° СЃРїР°Рј.",
                        parse_mode="HTML",
                    )
                    await notify_admins(
                        bot_,
                        f"рџљ« <b>РђРІС‚Рѕ-Р°РЅС‚РёСЃРїР°Рј</b>\n"
                        f"рџ‘¤ {user_mention(user.id, user.full_name)}"
                        f" (<code>{user.id}</code>)\n"
                        f"рџ’¬ Р—Р°РіР»СѓС€РµРЅ РЅР° {label} Р·Р° СЃРїР°Рј.",
                        source_chat_id=chat_id,
                    )
                except Exception:
                    pass
            return

        # Antiflood (configurable)
        settings = await get_chat_settings(chat_id)

        if settings and settings.get("cleanup_locked"):
            try:
                await event.delete()
            except Exception:
                pass
            return

        af_enabled = settings["antiflood_enabled"] if settings else int(DEFAULT_ANTIFLOOD_ENABLED)
        af_limit   = settings["antiflood_limit"]   if settings else DEFAULT_ANTIFLOOD_LIMIT
        af_window  = (settings.get("antiflood_window") if settings else None) or FLOOD_WINDOW
        if af_enabled and af_limit > 0 and check_flood(chat_id, user.id, af_limit, af_window):
            try:
                await event.delete()
                until = datetime.now() + timedelta(seconds=DEFAULT_FLOOD_MUTE)
                await bot_.restrict_chat_member(
                    chat_id, user.id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until,
                )
                mins = DEFAULT_FLOOD_MUTE // 60
                label = f"{mins} РјРёРЅ." if mins < 60 else f"{mins // 60} С‡."
                await bot_.send_message(
                    chat_id,
                    f"вљЎ {user_mention(user.id, user.full_name)}"
                    f" Р·Р°РіР»СѓС€РµРЅ РЅР° {label} Р·Р° С„Р»СѓРґ.",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return

        # Locks
        locks = await get_locks(chat_id)
        if locks:
            reason: str | None = None
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
                    asyncio.create_task(_delete_after(msg))
                except Exception:
                    pass
                return

        # Blacklist
        if event.text:
            bl_enabled = (
                settings["blacklist_enabled"]
                if settings and settings["blacklist_enabled"] is not None
                else int(DEFAULT_BLACKLIST_ENABLED)
            )
            if bl_enabled:
                blacklist = await get_blacklist(chat_id)
                text_lower = event.text.lower()
                if BLACKLIST_USE_MORPHOLOGY:
                    matched = _check_blacklist_morph(text_lower, blacklist)
                else:
                    matched = any(
                        re.search(r"\b" + re.escape(row["word"]) + r"\b", text_lower)
                        for row in blacklist
                    )
                if matched:
                    try:
                        await event.delete()
                        msg = await bot_.send_message(
                            chat_id,
                            f"вљ пёЏ РЎРѕРѕР±С‰РµРЅРёРµ {user_mention(user.id, user.full_name)}"
                            f" СѓРґР°Р»РµРЅРѕ (Р·Р°РїСЂРµС‰С‘РЅРЅРѕРµ СЃР»РѕРІРѕ).",
                            parse_mode="HTML",
                        )
                        asyncio.create_task(_delete_after(msg))
                    except Exception:
                        pass
                    return

        return await handler(event, data)
