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
from services import onboarding
from services.quests import increment_metric as quest_increment_metric
from services.achievements import increment_metric as ach_increment_metric, format_achievement_notification
from services.utils import safe_html

anti_spam_cache: dict[int, float] = {}

_QUEST_METRIC_LABELS: dict[str, str] = {
    "messages_in_chat_today":        "Написать сообщений",
    "pet_feeds_today":               "Накормить питомца",
    "gacha_spins_today":             "Крутить гачу",
    "expeditions_today":             "Экспедиций",
    "warps_to_distinct_users_today": "Варп разным игрокам",
    "auction_bids_today":            "Ставка на аукцион",
    "warps_hug_distinct_today":      "Обнять разных игроков",
    "rare_or_better_pet_dups_today": "Rare+ дубликатов",
    "pet_level_ups_today":           "Уровень питомца поднят",
}


def _notify_achievements(bot, chat_id: int, grants: list) -> None:
    """Fire-and-forget achievement notifications in chat."""
    import asyncio
    text = format_achievement_notification(grants)
    if bot and text:
        asyncio.ensure_future(
            bot.send_message(chat_id, text, parse_mode="HTML")
        )


def _notify_starter_kit(bot, chat_id: int, user, kit: dict) -> None:
    """Block 10: приветствие новичку со стартовым набором (fire-and-forget)."""
    import asyncio
    if not bot:
        return
    name = safe_html(user.first_name or user.username or str(user.id))
    text = (
        f"🎉 <b>Добро пожаловать, {name}!</b>\n"
        f"Тебе выдан стартовый набор:\n"
        f"🐾 Питомец: {safe_html(kit['species_name'])}\n"
        f"🪙 +{int(kit['mora'])} Моры\n"
        f"💎 +{int(kit['diamonds'])} Алмазов (хватит на 1 алмазный спин)\n"
        f"🎟 +{kit['spin_tokens']} Жетон Гачи (бесплатный спин за Мору)\n\n"
        f"Загляни в «бот зоопарк» и «бот крутка» 🎲"
    )
    asyncio.ensure_future(bot.send_message(chat_id, text, parse_mode="HTML"))


def _notify_quest_completions(bot, chat_id: int, user, completed: list) -> None:
    """Fire-and-forget quest completion notifications — errors are silenced."""
    import asyncio
    for cq in completed:
        reward = cq.get("reward", {})
        parts: list[str] = []
        if reward.get("mora", 0) > 0:
            parts.append(f"+{int(reward['mora'])} 🪙")
        if reward.get("diamonds", 0) > 0:
            parts.append(f"+{reward['diamonds']} 💎")
        for iid, qty in reward.get("items", []):
            parts.append(f"+{qty}×{iid}")
        reward_str = ", ".join(parts) or "—"
        label = _QUEST_METRIC_LABELS.get(cq.get("metric", ""), "Задание")
        name = safe_html(user.first_name or user.username or str(user.id))
        if bot:
            asyncio.ensure_future(
                bot.send_message(
                    chat_id,
                    f"✅ <a href='tg://user?id={user.id}'>{name}</a> "
                    f"выполнил задание <b>«{label}»</b>!\n"
                    f"Награда: <b>{reward_str}</b>",
                    parse_mode="HTML",
                )
            )


async def db_middleware(
    handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
    event: TelegramObject,
    data: Dict[str, Any],
) -> Any:
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
                # Block 10: стартовый набор новичку (ровно один раз; no-op для всех
                # существующих игроков — у них onboarded=TRUE).
                try:
                    kit = await onboarding.grant_starter_kit(db, user.id)
                    if kit and chat_obj:
                        _notify_starter_kit(data.get("bot"), chat_obj.id, user, kit)
                except Exception as _oe:
                    logger.warning(f"onboarding kit error for {user.id}: {_oe}")
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

            if user and chat_obj and event.message and _is_group:
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

                # process_message_xp → chat_repo.increment_stats_and_get_xp which
                # updates BOTH user_chat_stats rolling counters AND daily_user_stats.
                # Single source of truth — no second INSERT needed here.
                await leveling.process_message_xp(
                    db, user.id, chat_obj.id, _tz
                )

                # Daily quest: messages_in_chat_today
                try:
                    completed = await quest_increment_metric(
                        db, user.id, chat_obj.id, "messages_in_chat_today", delta=1.0
                    )
                    if completed:
                        _notify_quest_completions(data.get("bot"), chat_obj.id, user, completed)
                except Exception:
                    pass

                # Achievement: talker (messages_total_global — глобальный счётчик)
                try:
                    ach_grants = await ach_increment_metric(
                        db, user.id, "messages_total_global", delta=1.0, chat_id=chat_obj.id
                    )
                    if ach_grants:
                        await db.commit()
                        _notify_achievements(data.get("bot"), chat_obj.id, ach_grants)
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
