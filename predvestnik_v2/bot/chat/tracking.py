"""Учёт сообщений в группах: основа для топов, стрика и чистки."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from aiogram.types import Message

from bot.config import config


def tz_delta() -> timedelta:
    m = re.match(r"\s*([+-]?\d+(?:\.\d+)?)\s*hour", config.timezone_offset or "")
    return timedelta(hours=float(m.group(1)) if m else 0)


def local_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) + tz_delta()


async def record_message(db, message: Message) -> None:
    user = message.from_user
    chat = message.chat
    if not user or user.is_bot or chat.type not in ("group", "supergroup"):
        return
    day = local_now().strftime("%Y-%m-%d")
    await db.execute(
        "INSERT INTO users (user_tg_id, user_tg_username) VALUES (?, ?) "
        "ON CONFLICT (user_tg_id) DO UPDATE SET user_tg_username = EXCLUDED.user_tg_username",
        (user.id, user.username),
    )
    await db.execute(
        "INSERT INTO chat_settings (chat_id, chat_title) VALUES (?, ?) "
        "ON CONFLICT (chat_id) DO UPDATE SET chat_title = EXCLUDED.chat_title",
        (chat.id, chat.title),
    )
    await db.execute(
        "INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, user_messages_count_all_time, is_left) "
        "VALUES (?, ?, 1, FALSE) "
        "ON CONFLICT (user_tg_id, chat_tg_id) DO UPDATE SET "
        "user_messages_count_all_time = user_chat_stats.user_messages_count_all_time + 1, "
        "last_message_at = NOW(), is_left = FALSE",
        (user.id, chat.id),
    )
    await db.execute(
        "INSERT INTO daily_user_stats (user_id, chat_id, date, message_count) VALUES (?, ?, ?, 1) "
        "ON CONFLICT (user_id, chat_id, date) DO UPDATE SET "
        "message_count = daily_user_stats.message_count + 1",
        (user.id, chat.id, day),
    )
    await touch_streak(db, user.id)
    commit = getattr(db, "commit", None)
    if commit:
        await commit()
    # Бот и Mini App в production живут в одном процессе. Онлайн-игрок получает
    # только дельту своей активности; для офлайн-игроков запросов и очередей нет.
    try:
        from FastAPI.notifications import notify
        await notify(user.id, {"type": "activity_changed", "messages_delta": 1})
    except Exception:
        # Учёт сообщения важнее необязательного live-сигнала.
        pass


async def touch_streak(db, user_id: int) -> None:
    """Активность в любом чате засчитывает сегодняшний день стрика (общий на все чаты).

    Строка daily_login с chat_id = 0; last_login — местное время.
    """
    now = local_now()
    today = now.date()
    await db.execute(
        "INSERT INTO daily_login (user_id, chat_id, streak, best_streak, last_login) VALUES (?, 0, 1, 1, ?) "
        "ON CONFLICT (user_id, chat_id) DO UPDATE SET "
        "streak = CASE WHEN daily_login.last_login::date = ? THEN daily_login.streak "
        "  WHEN daily_login.last_login::date = ? THEN daily_login.streak + 1 ELSE 1 END, "
        "best_streak = GREATEST(COALESCE(daily_login.best_streak, 0), daily_login.streak, "
        "  CASE WHEN daily_login.last_login::date = ? THEN daily_login.streak + 1 ELSE 1 END), "
        "last_login = ?",
        (user_id, now, today, today - timedelta(days=1), today - timedelta(days=1), now),
    )
