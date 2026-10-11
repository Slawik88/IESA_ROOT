"""Учёт сообщений в группах: основа для топов, стрика и чистки."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from aiogram.types import Message

from bot.config import config
from services import name_history


def tz_delta() -> timedelta:
    m = re.match(r"\s*([+-]?\d+(?:\.\d+)?)\s*hour", config.timezone_offset or "")
    return timedelta(hours=float(m.group(1)) if m else 0)


def local_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) + tz_delta()


# ── «С какого числа в чате» ────────────────────────────────────────────────
# Telegram не отдаёт настоящую дату вступления, поэтому считаем по следам бота:
#  - joined_at — когда бот впервые завёл игрока в этом чате;
#  - membership_since — то же, но колонку добавили позже: у старых игроков там дата
#    миграции, а не вступления, поэтому одна она верить нельзя;
#  - первый день из daily_user_stats — когда игрок впервые написал (местная дата);
#  - rejoined_at — когда игрок вернулся после ухода (ставится при входе и при первом
#    сообщении после ухода, см. members.py и record_message).
# Первое появление — самая ранняя из первых трёх; нынешнее пребывание — с возвращения.
PRESENCE_SQL = (
    "s.joined_at, s.membership_since, s.rejoined_at, "
    "(SELECT MIN(d.date) FROM daily_user_stats d WHERE d.chat_id = s.chat_tg_id AND d.user_id = s.user_tg_id)"
)


def _naive_utc(dt) -> datetime | None:
    if not isinstance(dt, datetime):
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _first_day_utc(first_day) -> datetime | None:
    try:
        return datetime.combine(date.fromisoformat(str(first_day)[:10]), datetime.min.time()) - tz_delta()
    except (TypeError, ValueError):
        return None


def first_seen_at(joined_at, membership_since, first_day) -> datetime | None:
    """Самое раннее известное присутствие игрока в чате (naive UTC)."""
    known = [x for x in (_naive_utc(joined_at), _naive_utc(membership_since), _first_day_utc(first_day)) if x]
    return min(known) if known else None


def stay_start(joined_at, membership_since, rejoined_at, first_day) -> datetime | None:
    """Начало нынешнего пребывания в чате (naive UTC): возвращение или первое появление."""
    first = first_seen_at(joined_at, membership_since, first_day)
    back = _naive_utc(rejoined_at)
    return back if back and (not first or back > first) else first


@dataclass(frozen=True)
class Presence:
    first_seen: date      # местная дата первого появления
    since: date           # местная дата начала нынешнего пребывания
    rejoined: bool
    days: int             # дней в чате с `since` (сегодня — 0)


def presence_of(joined_at, membership_since, rejoined_at, first_day) -> Presence | None:
    first = first_seen_at(joined_at, membership_since, first_day)
    if not first:
        return None
    start = stay_start(joined_at, membership_since, rejoined_at, first_day) or first
    shift = tz_delta()
    first_d, since_d = (first + shift).date(), (start + shift).date()
    return Presence(first_d, since_d, since_d > first_d, max(0, (local_now().date() - since_d).days))


_username_seen: dict[int, str] = {}


async def _claim_username(db, user_id: int, username: str | None) -> None:
    """Ник в Telegram принадлежит одному человеку. Если он сменил его, а старый владелец остался в базе с этим же ником,
    команды «бот перевод @ник» находили не того. Чистим только при смене: лишний запрос на каждое сообщение не нужен."""
    key = (username or "").lower()
    if not key or _username_seen.get(user_id) == key:
        return
    await db.execute("UPDATE users SET user_tg_username = NULL WHERE LOWER(user_tg_username) = ? AND user_tg_id <> ?",
                     (key, user_id))
    _username_seen[user_id] = key


async def record_message(db, message: Message) -> None:
    user = message.from_user
    chat = message.chat
    if not user or user.is_bot or chat.type not in ("group", "supergroup"):
        return
    day = local_now().strftime("%Y-%m-%d")
    await db.execute(
        "INSERT INTO users (user_tg_id, user_tg_username, user_tg_name) VALUES (?, ?, ?) "
        "ON CONFLICT (user_tg_id) DO UPDATE SET user_tg_username = EXCLUDED.user_tg_username, "
        "user_tg_name = COALESCE(EXCLUDED.user_tg_name, users.user_tg_name)",
        (user.id, user.username, (getattr(user, "full_name", None) or "").strip()[:128] or None),
    )
    await _claim_username(db, user.id, user.username)
    await name_history.record(db, user.id, user.username, getattr(user, "full_name", None))
    await db.execute(
        "INSERT INTO chat_settings (chat_id, chat_title) VALUES (?, ?) "
        "ON CONFLICT (chat_id) DO UPDATE SET chat_title = EXCLUDED.chat_title, bot_left_at = NULL",   # пишут в чат — бот в нём
        (chat.id, chat.title),
    )
    await db.execute(
        "INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, user_messages_count_all_time, is_left) "
        "VALUES (?, ?, 1, FALSE) "
        "ON CONFLICT (user_tg_id, chat_tg_id) DO UPDATE SET "
        "user_messages_count_all_time = user_chat_stats.user_messages_count_all_time + 1, "
        "last_message_at = NOW(), is_left = FALSE, "
        "rejoined_at = CASE WHEN COALESCE(user_chat_stats.is_left, FALSE) THEN NOW() "
        "ELSE user_chat_stats.rejoined_at END",
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
