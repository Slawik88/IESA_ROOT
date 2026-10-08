"""Метрики для админки: мини-приложение, команды бота, активность в чатах.

Сайт — существующая таблица site_analytics (мини-приложение само шлёт открытия вкладок
и время на них). Команды бота — новые суточные счётчики bot_command_daily и bot_user_daily
(пишутся при каждой выполненной команде). Чаты — существующая daily_user_stats.
Сутки — по местному времени бота (TIMEZONE_OFFSET), как у топов и стрика.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from bot.chat.tracking import local_now, tz_delta

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS bot_command_daily (
        day     DATE   NOT NULL,
        command TEXT   NOT NULL,
        place   TEXT   NOT NULL,          -- group | private
        uses    INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (day, command, place)
    )""",
    """CREATE TABLE IF NOT EXISTS bot_user_daily (
        day      DATE   NOT NULL,
        user_id  BIGINT NOT NULL,
        place    TEXT   NOT NULL,
        commands INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (day, user_id, place)
    )""",
)

PAGE_TITLES = {
    "profile": "Профиль", "arena": "Игры", "looks": "Образы", "questlog": "Задания", "top": "Топ", "more": "Ещё",
    "achievements-v1": "Достижения", "chat-tracker": "Чаты", "chests": "Сундуки", "exchange-v1": "Биржа",
    "help": "Помощь", "news": "Новости", "pets": "Питомцы", "public-profile": "Чужой профиль",
    "settings": "Настройки", "store": "Магазин",
}
PERIODS = (1, 7, 30)


async def ensure_schema(db) -> None:
    for sql in STATEMENTS:
        await db.execute(sql)


def today() -> date:
    return local_now().date()


async def record_command(db, command: str, user_id: int, place: str) -> None:
    day = today()
    await db.execute(
        "INSERT INTO bot_command_daily (day, command, place, uses) VALUES (?, ?, ?, 1) "
        "ON CONFLICT (day, command, place) DO UPDATE SET uses = bot_command_daily.uses + 1",
        (day, command, place))
    await db.execute(
        "INSERT INTO bot_user_daily (day, user_id, place, commands) VALUES (?, ?, ?, 1) "
        "ON CONFLICT (day, user_id, place) DO UPDATE SET commands = bot_user_daily.commands + 1",
        (day, user_id, place))


def _utc_start(day: date) -> datetime:
    """Начало местных суток в UTC без пояса (как пишет site_analytics через NOW())."""
    return datetime.combine(day, time()) - tz_delta()


async def _one(db, sql: str, args: tuple):
    async with db.execute(sql, args) as cur:
        return await cur.fetchone()


async def _all(db, sql: str, args: tuple):
    async with db.execute(sql, args) as cur:
        return await cur.fetchall()


async def _site(db, since_day: date, until_day: date) -> dict:
    start, end = _utc_start(since_day), _utc_start(until_day + timedelta(days=1))
    span = "visited_at >= ? AND visited_at < ?"
    row = await _one(db, f"SELECT COUNT(DISTINCT user_id), COUNT(DISTINCT session_id), COUNT(*), "
                         f"COALESCE(SUM(duration_sec), 0) FROM site_analytics WHERE {span}", (start, end))
    visitors, sessions, visits, seconds = (int(x) for x in row)
    rows = await _all(db, f"SELECT tab, COUNT(*), COUNT(DISTINCT user_id), COALESCE(SUM(duration_sec), 0) "
                          f"FROM site_analytics WHERE {span} GROUP BY tab ORDER BY 2 DESC LIMIT 60", (start, end))
    pages, subpages = [], []
    for tab, n, users, secs in rows:
        item = {"tab": tab, "title": PAGE_TITLES.get(tab, tab), "visits": int(n), "users": int(users),
                "seconds": int(secs), "avg_seconds": round(int(secs) / int(n)) if n else 0}
        (subpages if "/" in tab else pages).append(item)
    shift = int(tz_delta().total_seconds())
    daily = await _all(db, f"SELECT (visited_at + (? * INTERVAL '1 second'))::date AS d, COUNT(DISTINCT user_id), "
                           f"COALESCE(SUM(duration_sec), 0) FROM site_analytics WHERE {span} GROUP BY d ORDER BY d",
                       (shift, start, end))
    return {"visitors": visitors, "sessions": sessions, "visits": visits, "seconds": seconds,
            "avg_seconds_per_visitor": round(seconds / visitors) if visitors else 0,
            "pages": pages, "subpages": subpages[:20],
            "daily": {str(d): {"users": int(u), "seconds": int(s)} for d, u, s in daily}}


async def _bot(db, since_day: date, until_day: date) -> dict:
    span = "day BETWEEN ? AND ?"
    args = (since_day, until_day)
    by_place = {r[0]: int(r[1]) for r in await _all(
        db, f"SELECT place, SUM(uses) FROM bot_command_daily WHERE {span} GROUP BY place", args)}
    users = {r[0]: int(r[1]) for r in await _all(
        db, f"SELECT place, COUNT(DISTINCT user_id) FROM bot_user_daily WHERE {span} GROUP BY place", args)}
    total_users = int((await _one(db, f"SELECT COUNT(DISTINCT user_id) FROM bot_user_daily WHERE {span}", args))[0])
    top = await _all(db, f"SELECT command, SUM(uses) FILTER (WHERE place = 'group'), "
                         f"SUM(uses) FILTER (WHERE place = 'private'), SUM(uses) FROM bot_command_daily "
                         f"WHERE {span} GROUP BY command ORDER BY 4 DESC LIMIT 20", args)
    daily = await _all(db, f"SELECT day, COUNT(DISTINCT user_id), SUM(commands) FROM bot_user_daily "
                           f"WHERE {span} GROUP BY day ORDER BY day", args)
    return {"commands": sum(by_place.values()), "commands_group": by_place.get("group", 0),
            "commands_private": by_place.get("private", 0), "users": total_users,
            "users_group": users.get("group", 0), "users_private": users.get("private", 0),
            "top": [{"command": c, "group": int(g or 0), "private": int(p or 0), "total": int(t)} for c, g, p, t in top],
            "daily": {str(d): {"users": int(u), "commands": int(n)} for d, u, n in daily}}


async def _chats(db, since_day: date, until_day: date) -> dict:
    args = (since_day.isoformat(), until_day.isoformat())
    span = "date BETWEEN ? AND ?"
    row = await _one(db, f"SELECT COALESCE(SUM(message_count), 0), COUNT(DISTINCT user_id), COUNT(DISTINCT chat_id) "
                         f"FROM daily_user_stats WHERE {span} AND chat_id < 0", args)
    top = await _all(db, f"SELECT d.chat_id, c.chat_title, SUM(d.message_count), COUNT(DISTINCT d.user_id) "
                         f"FROM daily_user_stats d LEFT JOIN chat_settings c ON c.chat_id = d.chat_id "
                         f"WHERE {span} AND d.chat_id < 0 GROUP BY d.chat_id, c.chat_title ORDER BY 3 DESC LIMIT 10", args)
    daily = await _all(db, f"SELECT date, SUM(message_count), COUNT(DISTINCT user_id) FROM daily_user_stats "
                           f"WHERE {span} AND chat_id < 0 GROUP BY date ORDER BY date", args)
    return {"messages": int(row[0]), "users": int(row[1]), "chats": int(row[2]),
            "top": [{"id": int(i), "title": t or str(i), "messages": int(m), "users": int(u)} for i, t, m, u in top],
            "daily": {str(d): {"messages": int(m), "users": int(u)} for d, m, u in daily}}


async def dashboard(db, days: int) -> dict:
    days = days if days in PERIODS else 1
    until_day = today()
    since_day = until_day - timedelta(days=days - 1)
    site = await _site(db, since_day, until_day)
    bot = await _bot(db, since_day, until_day)
    chats = await _chats(db, since_day, until_day)
    # Уникальные люди хоть где-то: сайт, команды бота, сообщения в чатах.
    start, end = _utc_start(since_day), _utc_start(until_day + timedelta(days=1))
    everyone = int((await _one(
        db, "SELECT COUNT(*) FROM (SELECT user_id FROM site_analytics WHERE visited_at >= ? AND visited_at < ? "
            "UNION SELECT user_id FROM bot_user_daily WHERE day BETWEEN ? AND ? "
            "UNION SELECT user_id FROM daily_user_stats WHERE date BETWEEN ? AND ? AND chat_id < 0) x",
        (start, end, since_day, until_day, since_day.isoformat(), until_day.isoformat())))[0])
    totals = await _one(db, "SELECT (SELECT COUNT(*) FROM users), (SELECT COUNT(*) FROM chat_settings WHERE chat_id < 0)", ())
    day_list = [(since_day + timedelta(days=i)).isoformat() for i in range(days)]
    return {"days": days, "since": since_day.isoformat(), "until": until_day.isoformat(), "day_list": day_list,
            "everyone": everyone, "players_total": int(totals[0]), "chats_total": int(totals[1]),
            "site": site, "bot": bot, "chats": chats}
