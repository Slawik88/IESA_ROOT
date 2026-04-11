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
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatPermissions, Message

from config import (
    DEFAULT_ANTIFLOOD_ENABLED, DEFAULT_ANTIFLOOD_LIMIT,
    DEFAULT_BLACKLIST_ENABLED, DEFAULT_FLOOD_MUTE, DEVELOPER_ID, FLOOD_WINDOW,
    LEVEL_UP_ANNOUNCE, XP_COOLDOWN, XP_PER_MESSAGE, BLACKLIST_USE_MORPHOLOGY,
    MORA_DAILY_BONUS, MORA_LEVELUP_BONUS, MORA_MSG_CHANCE, MORA_MSG_COOLDOWN,
    MORA_MSG_MAX, MORA_MSG_MIN, MORA_QUEST_REWARD, MORA_STREAK_BONUS,
    AF2_ANTISPAM_LIMIT,
)
from database.db import (
    add_mora, add_xp_in_chat,
    apply_pending_import, apply_pending_marriages,
    check_daily_mora,
    get_active_chat_buff, get_blacklist, get_chat_settings, get_locks,
    get_user_quest, get_user_stats, get_xp_boost_active,
    increment_cleanup_count, increment_message_count_chat,
    is_maintenance_mode, is_user_single, mark_quest_rewarded,
    quest_tick, set_newbie_shield,
    upsert_chat, upsert_user, upsert_user_stats,
    get_admin_group_ids, is_test_chat,
)
from services.recent_users import remember_user
from utils.flood import check_flood, check_spam, check_smart_flood, get_af2_flag, is_af2_cfg_stale, set_af2_cfg
from utils.helpers import bot_today, notify_admins, user_mention
from utils.ranks import rank_level

import logging
_log = logging.getLogger("middleware.automod")

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

# ── Telegram admin cache (avoids repeated getChatAdministrators calls) ────────
_tg_admin_cache: dict[int, tuple[frozenset, float]] = {}  # chat_id → (ids, expires_at)
_TG_ADMIN_CACHE_TTL = 300.0  # 5 minutes

# ── Admin soft-mute state (simulated mute for TG admins bot cannot restrict) ─
_admin_soft_mute: dict[tuple[int, int], float] = {}  # (chat_id, user_id) → until_ts

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
    except Exception as _e:
        _log.debug("%s", _e)


def _is_bot_command(event: Message) -> bool:
    """Return True if this message is a bot command ('бот ...')."""
    text = (event.text or event.caption or "").strip().lower()
    return text.startswith("бот ")


async def _get_tg_admins(bot: Bot, chat_id: int) -> frozenset:
    """Return cached frozenset of non-bot Telegram admin user IDs for chat_id.

    Uses a 5-minute in-memory TTL cache to avoid repeated API calls per message.
    On failure returns the stale cache entry (if any) or an empty frozenset.
    """
    now = time.time()
    cached = _tg_admin_cache.get(chat_id)
    if cached and cached[1] > now:
        return cached[0]
    try:
        members = await bot.get_chat_administrators(chat_id)
        ids = frozenset(m.user.id for m in members if not m.user.is_bot)
        _tg_admin_cache[chat_id] = (ids, now + _TG_ADMIN_CACHE_TTL)
        return ids
    except Exception:
        _log.debug("get_chat_administrators failed chat=%s", chat_id)
        return cached[0] if cached else frozenset()


async def _process_economy(user_id: int, chat_id: int, event: Message) -> None:
    """Award daily Mora, random Mora drop, and advance message-type quest."""
    today = bot_today()
    key = (user_id, chat_id)

    # Daily bonus + 7-day streak
    if len(_mora_daily_checked) > 2_000:
        stale = [k for k, v in _mora_daily_checked.items() if v != today]
        for k in stale:
            del _mora_daily_checked[k]
        # If still too large (everyone active today), just trim oldest half
        if len(_mora_daily_checked) > 2_000:
            for k in list(_mora_daily_checked)[:1_000]:
                del _mora_daily_checked[k]
    if _mora_daily_checked.get(key) != today:
        _mora_daily_checked[key] = today
        is_daily, _streak, streak_bonus = await check_daily_mora(user_id, chat_id)
        if is_daily:
            await add_mora(user_id, chat_id, MORA_DAILY_BONUS)
            try:
                from api.economy import log_wallet_tx as _lwt
                await _lwt(user_id, chat_id, 'in', MORA_DAILY_BONUS, 'daily_bonus', '📅 Ежедневный бонус')
            except Exception as _e:
                _log.debug("%s", _e)
            if streak_bonus:
                await add_mora(user_id, chat_id, MORA_STREAK_BONUS)
                try:
                    from api.economy import log_wallet_tx as _lwt
                    await _lwt(user_id, chat_id, 'in', MORA_STREAK_BONUS, 'streak_bonus', '🔥 7-дневный стрик')
                except Exception as _e:
                    _log.debug("%s", _e)
                try:
                    await event.answer(
                        f"🔥 {user_mention(user_id, event.from_user.full_name)}"
                        f" — 7-дневный стрик! <b>+{MORA_STREAK_BONUS} Моры</b> 🪙",
                        parse_mode="HTML",
                    )
                except Exception as _e:
                    _log.debug("%s", _e)

    # Random Mora drop (with per-user cooldown)
    now = time.monotonic()
    if now - _mora_cooldown.get(key, 0) >= MORA_MSG_COOLDOWN:
        single   = await is_user_single(user_id, chat_id)
        chance   = 0.20 if single else MORA_MSG_CHANCE
        # Talent: mora_harvest adds % chance
        try:
            from database.db import get_talent_effect as _gte
            _mora_bonus = await _gte(user_id, "mora_drop_chance")
            if _mora_bonus > 0:
                chance = min(chance + _mora_bonus / 100.0, 0.90)
        except Exception as _e:
            _log.debug("%s", _e)
        min_drop = MORA_MSG_MIN + (1 if single else 0)
        max_drop = MORA_MSG_MAX + (1 if single else 0)
        if random.random() < chance:
            _mora_cooldown[key] = now
            drop = random.randint(min_drop, max_drop)
            if 0 <= datetime.now(_TZ_ZURICH).hour < 6:
                drop *= 2  # night bonus
            # ── Бафф mora_boost от подарков (trip/crown/castle) ─────────
            try:
                from database.db import get_active_buffs as _gab
                _buffs = await _gab(user_id, chat_id)
                for _b in _buffs:
                    _bt = _b.get("buff_type") or _b.get("type", "")
                    if _bt == "mora_boost_20":
                        drop = int(drop * 1.20); break
                    elif _bt == "mora_boost_15":
                        drop = int(drop * 1.15); break
                    elif _bt == "mora_boost_10":
                        drop = int(drop * 1.10); break
            except Exception as _e:
                _log.debug("mora_boost check: %s", _e)
            await add_mora(user_id, chat_id, drop)
            try:
                from api.economy import log_wallet_tx as _lwt
                await _lwt(user_id, chat_id, 'in', drop, 'msg_drop', '💬 Случайный дроп')
            except Exception as _e:
                _log.debug("%s", _e)

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
            try:
                from api.economy import log_wallet_tx as _lwt
                await _lwt(user_id, chat_id, 'in', mora_reward, 'daily_quest', '🎯 Ежедневное задание')
            except Exception as _e:
                _log.debug("%s", _e)
            await mark_quest_rewarded(user_id, chat_id, today)
            try:
                await event.answer(
                    f"🎉 {user_mention(user_id, event.from_user.full_name)}"
                    f" выполнил ежедневное задание!"
                    f" <b>+{quest['xp']} XP</b>  <b>+{mora_reward} Моры</b> 🪙",
                    parse_mode="HTML",
                )
            except Exception as _e:
                _log.debug("%s", _e)


async def _process_xp(user_id: int, chat_id: int, event: Message, bot=None) -> None:
    """Award per-message XP (once per cooldown). Announce level-ups."""
    # Check feat_xp_gain toggle
    try:
        _xp_settings = await get_chat_settings(chat_id)
        if _xp_settings and _xp_settings.get("feat_xp_gain") == 0:
            return
    except Exception as _e:
        _log.debug("%s", _e)

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
    # ── Талант: xp_bonus_pct увеличивает XP за сообщения ──────────
    try:
        from database.db import get_talent_effect as _gte
        _xp_pct = await _gte(user_id, "xp_bonus_pct")
        if _xp_pct > 0:
            xp = max(1, int(xp * (1 + _xp_pct / 100.0)))
    except Exception as _e:
        _log.debug("xp_bonus_pct: %s", _e)

    new_xp, new_level, leveled_up = await add_xp_in_chat(user_id, chat_id, xp)
    if leveled_up:
        await add_mora(user_id, chat_id, MORA_LEVELUP_BONUS)
        try:
            from api.economy import log_wallet_tx as _lwt
            await _lwt(user_id, chat_id, 'in', MORA_LEVELUP_BONUS, 'level_up', f'💠 Бонус за уровень {new_level}')
        except Exception as _e:
            _log.debug("%s", _e)
        # Блок 2: выдать очки таланта и шарды за уровень
        try:
            from database.db import award_talent_points, award_level_shards
            tp_gained = await award_talent_points(user_id, new_level)
            shards_given = await award_level_shards(user_id, chat_id, new_level)
        except Exception:
            tp_gained = 0
            shards_given = []
        try:
            from api.achievements import check_and_award as _ach
            await _ach(user_id, chat_id, "level", new_level, bot=bot,
                       username=event.from_user.full_name if event.from_user else "")
        except Exception as _e:
            _log.debug("%s", _e)
        if LEVEL_UP_ANNOUNCE:
            shard_str = ""
            if shards_given:
                shard_str = "  " + "  ".join(f"+{s['amount']} {s['emoji']}" for s in shards_given)
            tp_str = f"  <b>+{tp_gained} TP 🎯</b>" if tp_gained else ""
            try:
                await event.answer(
                    f"🌟 {user_mention(user_id, event.from_user.full_name)}"
                    f" достиг <b>{new_level} уровня</b>!"
                    f" (XP: {new_xp}) <b>+{MORA_LEVELUP_BONUS} Моры</b> 🪙{tp_str}{shard_str}",
                    parse_mode="HTML",
                )
            except Exception as _e:
                _log.debug("%s", _e)


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
            _log.debug("SKIP pre-start msg uid=%s chat=%s", user.id, event.chat.id)
            return

        is_stale = (time.time() - event.date.timestamp()) > 30
        in_group = event.chat.type in ("group", "supergroup")

        # is_admin_chat: dedicated admin/ops chats — fully isolated (no economy, no automod)
        is_admin_chat = in_group and event.chat.id in get_admin_group_ids()
        # is_test_chat: flood-test polygons — skip economy, but STILL run automod
        is_test_polygon = in_group and is_test_chat(event.chat.id)
        is_isolated = is_admin_chat or is_test_polygon
        data["is_isolated_chat"] = is_isolated

        _log.debug(
            "MSG uid=%s (@%s) chat=%s [%s] isolated=%s stale=%s",
            user.id, user.username or "-", event.chat.id,
            event.chat.type, is_isolated, is_stale,
        )

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
        if is_admin_chat:
            _log.debug("ADMIN_CHAT chat=%s — fully isolated for uid=%s", event.chat.id, user.id)
            # Cleanup mode: delete messages from non-privileged users even in admin chats.
            # (set_chat_permissions is NOT used for locking — restrictChatMember(all_true)
            # reverts the user to the group default, so Telegram-level locking broke staff.
            # Now only the DB flag + middleware deletion are used.)
            _ac_settings = await get_chat_settings(event.chat.id)
            if _ac_settings and _ac_settings.get("cleanup_locked"):
                _ac_privileged = bool(DEVELOPER_ID and user.id == DEVELOPER_ID)
                if not _ac_privileged:
                    _ac_stats = await get_user_stats(user.id, event.chat.id)
                    _ac_rank = (_ac_stats["rank"] if _ac_stats else None) or "user"
                    if rank_level(_ac_rank) < rank_level("co_owner"):
                        try:
                            await event.delete()
                        except Exception as _e:
                            _log.debug("%s", _e)
                        return
            return await handler(event, data)

        # Test polygon chats: skip economy only — automod still runs below
        if is_test_polygon:
            _log.debug("TEST_POLYGON chat=%s — economy skip for uid=%s", event.chat.id, user.id)

        # ── Maintenance mode: count messages but skip economy/games ──────
        _in_maintenance = False
        if in_group and not is_isolated:
            try:
                _in_maintenance = await is_maintenance_mode()
            except Exception as _e:
                _log.debug("%s", _e)
            if _in_maintenance and not (DEVELOPER_ID and user.id == DEVELOPER_ID):
                _log.debug("MAINTENANCE uid=%s chat=%s — metrics only", user.id, event.chat.id)
                await upsert_user_stats(user.id, event.chat.id)
                from services.message_buffer import buffer_message
                buffer_message(user.id, event.chat.id)
                await increment_message_count_chat(user.id, event.chat.id)
                await increment_cleanup_count(event.chat.id, user.id)
                return await handler(event, data)

        # ── Group economy (non-isolated groups only) ───────────────────────
        if in_group and not is_isolated:
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
                    _bot_for_ach = data.get("bot")
                    await _ach(user.id, event.chat.id, "messages", msg_count,
                               bot=_bot_for_ach, username=user.full_name or "")
                except Exception as _e:
                    _log.debug("%s", _e)

            # Mora + quests
            await _process_economy(user.id, event.chat.id, event)

            # XP + level-up
            await _process_xp(user.id, event.chat.id, event, bot=data.get("bot"))

            # Блок 2: тик квеста новичка
            try:
                from database.db import tick_newbie_quest, claim_newbie_quest_reward
                nq = await tick_newbie_quest(user.id, event.chat.id)
                if nq and nq.get("just_completed"):
                    result = await claim_newbie_quest_reward(user.id, event.chat.id)
                    if result.get("ok"):
                        try:
                            await event.answer(
                                f"🎉 {user_mention(user.id, event.from_user.full_name)}"
                                f" выполнил Квест Новичка — 100 сообщений за 7 дней!\n"
                                f"<b>+200 🪙 +300 XP +5 осколков</b>\n"
                                f"⚡ Весь чат получил бафф +10% XP на 24 часа!",
                                parse_mode="HTML",
                            )
                        except Exception as _e:
                            _log.debug("%s", _e)
            except Exception as _e:
                _log.debug("%s", _e)

        # в”Ђв”Ђ Automod (groups only) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
        if not in_group:
            return await handler(event, data)

        stats = await get_user_stats(user.id, event.chat.id)
        user_rank = (stats["rank"] if stats else None) or "user"

        # owner / developer — hack-detection mode: check patterns but never mute,
        # only send a 🚨 priority alert to admins if anomaly detected.
        _is_hack_detection = (
            (DEVELOPER_ID and user.id == DEVELOPER_ID)
            or rank_level(user_rank) >= rank_level("owner")
        )

        bot_: Bot = data["bot"]
        chat_id = event.chat.id

        # Antiflood (configurable) — load settings once for this message
        settings = await get_chat_settings(chat_id)

        # ── Bot kill-switch: if bot_disabled=1, silently ignore all messages ──
        # Developer always bypasses this to allow re-enabling via commands.
        if (
            settings is not None
            and bool(settings.get("bot_disabled"))
            and not (DEVELOPER_ID and user.id == DEVELOPER_ID)
        ):
            return  # Bot fully disabled for this chat — skip all processing

        # Feature flag: feat_antispam (gates both Token-Bucket antispam and Smart Antiflood 2.0)
        _feat_antispam = True
        if settings is not None:
            try:
                _feat_antispam = bool(settings["feat_antispam"] != 0)
            except (KeyError, IndexError):
                _feat_antispam = True

        # ── Telegram admin check (cached, 5 min TTL) + soft-mute enforcement ──────
        _tg_admins = await _get_tg_admins(bot_, chat_id)
        _is_tg_admin = user.id in _tg_admins

        # Enforce an active admin soft-mute: delete their message and drop processing
        _soft_until = _admin_soft_mute.get((chat_id, user.id), 0)
        if _soft_until > time.time():
            if not is_stale:
                try:
                    await event.delete()
                except Exception as _e:
                    _log.debug("%s", _e)
            return

        # Antispam — Token Bucket (owner/developer skip mute but get hack-alert below)
        _is_bot_cmd = _is_bot_command(event)
        _antispam_on = bool(get_af2_flag("antispam_enabled", 1.0, chat_id))
        if _feat_antispam and _antispam_on and not _is_hack_detection and not _is_bot_cmd and check_spam(chat_id, user.id, AF2_ANTISPAM_LIMIT):
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
                    label = f"{mins} мин." if mins < 60 else f"{mins // 60} ч."
                    await bot_.send_message(
                        chat_id,
                        f"🚫 {user_mention(user.id, user.full_name)}"
                        f" заглушен на {label} за спам.",
                        parse_mode="HTML",
                    )
                    await notify_admins(
                        bot_,
                        f"🚫 <b>Авто-антиспам</b>\n"
                        f"👤 {user_mention(user.id, user.full_name)}"
                        f" (<code>{user.id}</code>)\n"
                        f"💬 Заглушен на {label} за спам.",
                        source_chat_id=chat_id,
                    )
                except Exception as _e:
                    _log.debug("%s", _e)
            return

        # Antiflood (configurable) — settings already loaded above
        if settings and settings.get("cleanup_locked"):
            # co_owner / owner / developer can still write during cleanup — never delete their messages
            _privileged_during_lock = (
                (DEVELOPER_ID and user.id == DEVELOPER_ID)
                or rank_level(user_rank) >= rank_level("co_owner")
            )
            if not _privileged_during_lock:
                try:
                    await event.delete()
                except Exception as _e:
                    _log.debug("%s", _e)
                return

        # ── Smart Antiflood 2.0 — always active when antispam feature is on ────
        # Refresh dynamic AF2 config from DB if TTL expired (cross-process miniapp update)
        if is_af2_cfg_stale(chat_id):
            try:
                from database.db import get_af2_config as _gaf2
                set_af2_cfg(chat_id, await _gaf2(chat_id))
            except Exception as _e:
                _log.debug("%s", _e)

        if _feat_antispam:
            _is_text = bool(event.text and not (event.text or "").strip().lower().startswith("бот "))
            _is_media = bool(event.photo or event.video or event.document)
            _is_animation = bool(event.animation)  # GIFs — separate from media, tracked as stickers
            _is_sticker = bool(event.sticker)
            _msg_count = stats["message_count"] if stats else 0

            sv = check_smart_flood(
                chat_id, user.id, _msg_count,
                message_id=event.message_id,
                is_text=_is_text,
                is_media=_is_media,
                is_sticker=_is_sticker,
                is_animation=_is_animation,
                media_group_id=event.media_group_id,
            )

            if sv.action == "warn" and not is_stale:
                # Legacy warn kept for any future warn-only verdicts
                try:
                    await event.delete()
                    await bot_.send_message(
                        chat_id,
                        f"💬 {user_mention(user.id, user.full_name)}"
                        f" полегче со стикерами/гифками 😊",
                        parse_mode="HTML",
                    )
                except Exception as _e:
                    _log.debug("%s", _e)
                return

            if sv.action == "mute" and not is_stale:
                _reason_labels = {
                    "text_spam": "текстовый спам",
                    "rate_exceeded": "слишком много сообщений подряд",
                    "media_raid": "медиа-рейд",
                    "mixed_attack": "смешанная атака",
                    "suspected_hack": "подозрение на взлом",
                    "sticker_gif_raid": "стикер/гиф-рейд",
                }
                reason_label = _reason_labels.get(sv.reason, "флуд")
                trust_label = {
                    "newcomer": "🆕 Новичок",
                    "regular": "👤 Обычный",
                    "trusted": "⭐ Доверенный",
                }.get(sv.trust, sv.trust)
                if sv.mute_seconds > 0:
                    mute_label = f"{sv.mute_seconds // 3600} ч." if sv.mute_seconds >= 3600 else f"{sv.mute_seconds // 60} мин."
                else:
                    mute_label = "бессрочно"

                if _is_hack_detection:
                    # — owner / developer: ALERT ONLY, bot cannot restrict chat admins —
                    rank_label = {"owner": "🔱 Владелец", "developer": "🛠 Разработчик"}.get(user_rank, f"🔱 {user_rank}")
                    try:
                        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(text="🚫 Бан по ID", callback_data=f"af2:ban:{chat_id}:{user.id}"),
                            InlineKeyboardButton(text="👢 Кик", callback_data=f"af2:kick:{chat_id}:{user.id}"),
                        ]])
                        await notify_admins(
                            bot_,
                            f"🚨 <b>ВОЗМОЖНЫЙ ВЗЛОМ АККАУНТА</b>\n\n"
                            f"{rank_label} {user_mention(user.id, user.full_name)}"
                            f" (<code>{user.id}</code>)\n"
                            f"⚠️ Паттерн: <b>{reason_label}</b>\n"
                            f"📊 Уровень доверия: {trust_label}\n"
                            f"💬 Чат: <code>{chat_id}</code>\n\n"
                            f"<i>Бот не может заглушить администратора ({mute_label}). Проверьте аккаунт вручную!</i>",
                            source_chat_id=chat_id,
                            reply_markup=keyboard,
                        )
                    except Exception:
                        _log.exception("Hack-detection alert failed chat=%s uid=%s", chat_id, user.id)
                    return await handler(event, data)  # let the message through — cannot restrict admins

                if _is_tg_admin:
                    # Telegram admin: cannot restrict via API — simulate mute via message deletion
                    # Delete the flood burst
                    if sv.delete_msg_ids:
                        try:
                            await bot_.delete_messages(chat_id, sv.delete_msg_ids)
                        except Exception:
                            for mid in sv.delete_msg_ids[-20:]:
                                try:
                                    await bot_.delete_message(chat_id, mid)
                                except Exception as _e:
                                    _log.debug("%s", _e)
                    try:
                        await event.delete()
                    except Exception as _e:
                        _log.debug("%s", _e)
                    # Register soft-mute so future messages are deleted until window expires
                    if sv.mute_seconds > 0:
                        _admin_soft_mute[(chat_id, user.id)] = time.time() + sv.mute_seconds
                        # Prune expired entries occasionally
                        if len(_admin_soft_mute) > 500:
                            _now_sm = time.time()
                            for _k in [k for k, v in _admin_soft_mute.items() if v <= _now_sm]:
                                del _admin_soft_mute[_k]
                    try:
                        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                        _ha_kb = InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(text="🚫 Бан по ID", callback_data=f"af2:ban:{chat_id}:{user.id}"),
                            InlineKeyboardButton(text="👢 Кик", callback_data=f"af2:kick:{chat_id}:{user.id}"),
                        ]])
                        await notify_admins(
                            bot_,
                            f"🚨 <b>ФЛУД ОТ АДМИНИСТРАТОРА</b>\n\n"
                            f"👤 {user_mention(user.id, user.full_name)}"
                            f" (<code>{user.id}</code>)\n"
                            f"⚠️ Паттерн: <b>{reason_label}</b>\n"
                            f"📊 Уровень доверия: {trust_label}\n"
                            f"💬 Чат: <code>{chat_id}</code>\n"
                            f"🔇 Мут: {mute_label} (удаление сообщений)\n\n"
                            f"<i>Telegram не позволяет ограничить администратора. "
                            f"Сообщения удаляются автоматически на {mute_label}.</i>",
                            source_chat_id=chat_id,
                            reply_markup=_ha_kb,
                        )
                    except Exception:
                        _log.exception("TG-admin flood alert failed chat=%s uid=%s", chat_id, user.id)
                    return

                try:
                    # Bulk-delete recent messages
                    if sv.delete_msg_ids:
                        try:
                            await bot_.delete_messages(chat_id, sv.delete_msg_ids)
                        except Exception:
                            for mid in sv.delete_msg_ids[-20:]:
                                try:
                                    await bot_.delete_message(chat_id, mid)
                                except Exception as _e:
                                    _log.debug("%s", _e)
                    else:
                        await event.delete()

                    # Apply mute — handle Telegram admins/owners gracefully
                    _restricted_ok = True
                    try:
                        if sv.mute_seconds > 0:
                            until = datetime.now() + timedelta(seconds=sv.mute_seconds)
                            await bot_.restrict_chat_member(
                                chat_id, user.id,
                                permissions=ChatPermissions(can_send_messages=False),
                                until_date=until,
                            )
                        else:
                            await bot_.restrict_chat_member(
                                chat_id, user.id,
                                permissions=ChatPermissions(can_send_messages=False),
                            )
                    except TelegramBadRequest as _tg_err:
                        _tg_msg = str(_tg_err).lower()
                        if (
                            "can't remove chat owner" in _tg_msg
                            or "not enough rights" in _tg_msg
                            or "user is an administrator" in _tg_msg
                        ):
                            # Stale cache or late-promoted admin — set soft-mute as fallback
                            _restricted_ok = False
                            _is_owner_err = "can't remove chat owner" in _tg_msg
                            if sv.mute_seconds > 0 and not _is_owner_err:
                                _admin_soft_mute[(chat_id, user.id)] = time.time() + sv.mute_seconds
                            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                            _ha_kb = InlineKeyboardMarkup(inline_keyboard=[[
                                InlineKeyboardButton(text="🚫 Бан по ID", callback_data=f"af2:ban:{chat_id}:{user.id}"),
                                InlineKeyboardButton(text="👢 Кик", callback_data=f"af2:kick:{chat_id}:{user.id}"),
                            ]])
                            _fallback_note = (
                                "<i>Бот не смог заглушить владельца чата. Проверьте вручную!</i>"
                                if _is_owner_err else
                                f"<i>Кэш прав устарел — сообщения удаляются на {mute_label}.</i>"
                            )
                            await notify_admins(
                                bot_,
                                f"🚨 <b>ФЛУД ОТ АДМИНИСТРАТОРА</b>\n\n"
                                f"👤 {user_mention(user.id, user.full_name)}"
                                f" (<code>{user.id}</code>)\n"
                                f"⚠️ Паттерн: <b>{reason_label}</b>\n"
                                f"📊 Уровень доверия: {trust_label}\n"
                                f"💬 Чат: <code>{chat_id}</code>\n\n"
                                + _fallback_note,
                                source_chat_id=chat_id,
                                reply_markup=_ha_kb,
                            )
                        else:
                            raise  # re-raise unexpected errors to outer except

                    if _restricted_ok:
                        if sv.mute_seconds > 0:
                            await bot_.send_message(
                                chat_id,
                                f"🛡 {user_mention(user.id, user.full_name)}"
                                f" заглушен на {mute_label} — {reason_label}.",
                                parse_mode="HTML",
                            )
                        else:
                            await bot_.send_message(
                                chat_id,
                                f"🛡 {user_mention(user.id, user.full_name)}"
                                f" заглушен бессрочно — {reason_label}.",
                                parse_mode="HTML",
                            )

                    # Admin notification with inline buttons (only when mute succeeded)
                    if _restricted_ok and sv.notify_admins:
                        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                        admin_text = (
                            f"🛡 <b>Антифлуд 2.0</b>\n\n"
                            f"👤 {user_mention(user.id, user.full_name)}"
                            f" (<code>{user.id}</code>)\n"
                            f"📊 Уровень: {trust_label} ({_msg_count} сообщ.)\n"
                            f"⚠️ Причина: <b>{reason_label}</b>\n"
                            f"🔇 Мут: {mute_label}\n"
                            f"💬 Чат: <code>{chat_id}</code>"
                        )
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(text="👢 Кик", callback_data=f"af2:kick:{chat_id}:{user.id}"),
                            InlineKeyboardButton(text="🚫 Бан по ID", callback_data=f"af2:ban:{chat_id}:{user.id}"),
                            InlineKeyboardButton(text="🔊 Размут", callback_data=f"af2:unmute:{chat_id}:{user.id}"),
                        ]])
                        await notify_admins(
                            bot_, admin_text,
                            source_chat_id=chat_id,
                            reply_markup=keyboard,
                        )
                except Exception:
                    _log.exception("Smart antiflood action failed chat=%s uid=%s", chat_id, user.id)
                return

            # ── Fallback: legacy configurable antiflood for regular users ─
            if sv.action == "allow" and sv.trust == "regular" and not _is_hack_detection:
                af_enabled = settings.get("antiflood_enabled", int(DEFAULT_ANTIFLOOD_ENABLED)) if settings else int(DEFAULT_ANTIFLOOD_ENABLED)
                af_limit = settings.get("antiflood_limit", DEFAULT_ANTIFLOOD_LIMIT) if settings else DEFAULT_ANTIFLOOD_LIMIT
                af_window = (settings.get("antiflood_window") if settings else None) or FLOOD_WINDOW
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
                        label = f"{mins} мин." if mins < 60 else f"{mins // 60} ч."
                        await bot_.send_message(
                            chat_id,
                            f"⚡ {user_mention(user.id, user.full_name)}"
                            f" заглушен на {label} за флуд.",
                            parse_mode="HTML",
                        )
                        trust_label = {"newcomer": "🆕 Новичок", "regular": "👤 Обычный", "trusted": "⭐ Доверенный"}.get(
                            sv.trust, "👤 Обычный"
                        )
                        await notify_admins(
                            bot_,
                            f"⚡ <b>Антифлуд (легаси)</b>\n\n"
                            f"👤 {user_mention(user.id, user.full_name)}"
                            f" (<code>{user.id}</code>)\n"
                            f"📊 {trust_label}\n"
                            f"🔇 Мут: {label}\n"
                            f"💬 Чат: <code>{chat_id}</code>",
                            source_chat_id=chat_id,
                        )
                    except Exception as _e:
                        _log.debug("%s", _e)
                    return

        # Locks
        locks = await get_locks(chat_id)
        if locks:
            reason: str | None = None
            if locks["links"] and event.text and _URL_RE.search(event.text):
                reason = "ссылки"
            elif locks["stickers"] and event.sticker:
                reason = "стикеры"
            elif locks["gifs"] and event.animation:
                reason = "гифки"
            elif locks["forwards"] and (
                event.forward_origin is not None
                or getattr(event, 'forward_from_chat', None) is not None
                or getattr(event, 'forward_from', None) is not None
            ):
                reason = "пересылку"
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
                    asyncio.create_task(_delete_after(msg))
                except Exception as _e:
                    _log.debug("%s", _e)
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
                            f"⚠️ Сообщение {user_mention(user.id, user.full_name)}"
                            f" удалено (запрещённое слово).",
                            parse_mode="HTML",
                        )
                        asyncio.create_task(_delete_after(msg))
                    except Exception as _e:
                        _log.debug("%s", _e)
                    return

        return await handler(event, data)
