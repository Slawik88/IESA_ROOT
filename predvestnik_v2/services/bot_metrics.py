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


async def _everyone(db, since_day: date, until_day: date) -> int:
    """Уникальные люди хоть где-то: сайт, команды бота, сообщения в чатах."""
    start, end = _utc_start(since_day), _utc_start(until_day + timedelta(days=1))
    return int((await _one(
        db, "SELECT COUNT(*) FROM (SELECT user_id FROM site_analytics WHERE visited_at >= ? AND visited_at < ? "
            "UNION SELECT user_id FROM bot_user_daily WHERE day BETWEEN ? AND ? "
            "UNION SELECT user_id FROM daily_user_stats WHERE date BETWEEN ? AND ? AND chat_id < 0) x",
        (start, end, since_day, until_day, since_day.isoformat(), until_day.isoformat())))[0])


async def _totals(db, since_day: date, until_day: date) -> dict:
    """Главные числа периода: для сравнения с предыдущим таким же."""
    start, end = _utc_start(since_day), _utc_start(until_day + timedelta(days=1))
    visitors = int((await _one(db, "SELECT COUNT(DISTINCT user_id) FROM site_analytics WHERE visited_at >= ? AND visited_at < ?",
                               (start, end)))[0])
    commands, bot_users = await _one(db, "SELECT COALESCE(SUM(commands), 0), COUNT(DISTINCT user_id) FROM bot_user_daily "
                                         "WHERE day BETWEEN ? AND ?", (since_day, until_day))
    messages, chat_users = await _one(db, "SELECT COALESCE(SUM(message_count), 0), COUNT(DISTINCT user_id) FROM daily_user_stats "
                                          "WHERE date BETWEEN ? AND ? AND chat_id < 0", (since_day.isoformat(), until_day.isoformat()))
    return {"everyone": await _everyone(db, since_day, until_day), "visitors": visitors, "commands": int(commands),
            "bot_users": int(bot_users), "messages": int(messages), "chat_users": int(chat_users)}


_retention_cache: tuple[float, date, dict] | None = None
RETENTION_TTL = 600.0


async def retention(db) -> dict:
    """Удержание: какая доля новых людей вернулась на следующий день, в течение 7 и 30 дней.

    «Новый» — впервые замечен в сообщениях чатов или командах бота. Для каждого окна берётся своя когорта, чтобы у всех
    уже прошёл нужный срок. Запрос тяжёлый, поэтому ответ держится десять минут."""
    import time as _time
    global _retention_cache
    day = today()
    if _retention_cache and _time.time() - _retention_cache[0] < RETENTION_TTL and _retention_cache[1] == day:
        return _retention_cache[2]
    act = ("SELECT user_id, date::date AS d FROM daily_user_stats WHERE chat_id < 0 AND date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' "
           "UNION SELECT user_id, day AS d FROM bot_user_daily")
    windows = (("d1", 1, 30, 1), ("d7", 7, 37, 7), ("d30", 30, 60, 30))
    parts, args = [], []
    for _key, within, back_from, back_to in windows:
        inside = "first.f BETWEEN ? AND ?"
        parts.append(f"COUNT(*) FILTER (WHERE {inside}), COUNT(*) FILTER (WHERE {inside} AND EXISTS ("
                     f"SELECT 1 FROM act a WHERE a.user_id = first.user_id AND a.d > first.f AND a.d <= first.f + {int(within)}))")
        args += [day - timedelta(days=back_from), day - timedelta(days=back_to)] * 2
    row = await _one(db, f"WITH act AS ({act}), first AS (SELECT user_id, MIN(d) AS f FROM act GROUP BY user_id) "
                         f"SELECT {', '.join(parts)} FROM first", tuple(args))
    out = {}
    for i, (key, _within, back_from, back_to) in enumerate(windows):
        cohort, back = int(row[i * 2]), int(row[i * 2 + 1])
        out[key] = {"cohort": cohort, "returned": back, "percent": round(back * 100 / cohort) if cohort else None,
                    "from": (day - timedelta(days=back_from)).isoformat(), "to": (day - timedelta(days=back_to)).isoformat()}
    _retention_cache = (_time.time(), day, out)
    return out


FUNNEL_MIN_TABS = 2        # «пошёл дальше первого экрана»: заглянул хотя бы в два раздела
FUNNEL_MIN_SECONDS = 60    # «остался»: в сумме минута и больше в приложении за период


async def funnel(db, since_day: date, until_day: date) -> dict:
    """Воронка мини-приложения за период: открыл → заглянул в два раздела → провёл минуту → потратил валюту.

    Каждый шаг входит в предыдущий (это те же люди, которые прошли дальше), поэтому проценты читаются как «сколько дошло».
    Отдельно: сколько из открывших приложение пользуются и командами бота. Журнала валюты может ещё не быть — тогда
    последний шаг пустой, а остальные считаются."""
    from datetime import timezone
    start, end = _utc_start(since_day), _utc_start(until_day + timedelta(days=1))
    row = await _one(
        db, "WITH v AS (SELECT user_id, COUNT(DISTINCT tab) AS tabs, COALESCE(SUM(duration_sec), 0) AS secs FROM site_analytics "
            "WHERE visited_at >= ? AND visited_at < ? GROUP BY user_id) "
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE tabs >= ?), COUNT(*) FILTER (WHERE tabs >= ? AND secs >= ?), "
            "COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM bot_user_daily b WHERE b.user_id = v.user_id AND b.day BETWEEN ? AND ?)) FROM v",
        (start, end, FUNNEL_MIN_TABS, FUNNEL_MIN_TABS, FUNNEL_MIN_SECONDS, since_day, until_day))
    opened, deeper, stayed, with_bot = (int(x) for x in row)
    spent = None
    try:
        spent = int((await _one(
            db, "WITH v AS (SELECT user_id FROM site_analytics WHERE visited_at >= ? AND visited_at < ? GROUP BY user_id "
                "HAVING COUNT(DISTINCT tab) >= ? AND COALESCE(SUM(duration_sec), 0) >= ?) "
                "SELECT COUNT(*) FROM v WHERE EXISTS (SELECT 1 FROM economic_ledger l WHERE l.user_id = v.user_id "
                "AND l.delta < 0 AND l.created_at >= ? AND l.created_at < ?)",
            (start, end, FUNNEL_MIN_TABS, FUNNEL_MIN_SECONDS, start.replace(tzinfo=timezone.utc), end.replace(tzinfo=timezone.utc))))[0])
    except Exception:   # журнала валюты ещё нет (чистая база)
        spent = None
    steps = [("opened", "Открыли приложение", opened), ("deeper", f"Заглянули в {FUNNEL_MIN_TABS} раздела и больше", deeper),
             ("stayed", f"Провели в приложении {FUNNEL_MIN_SECONDS // 60} мин и больше", stayed),
             ("spent", "Потратили игровую валюту", spent)]
    out, prev = [], None
    for key, title, n in steps:
        out.append({"key": key, "title": title, "users": n,
                    "of_first": round(n * 100 / opened) if (n is not None and opened) else None,
                    "of_prev": round(n * 100 / prev) if (n is not None and prev) else None})
        if n is not None:
            prev = n
    return {"steps": out, "with_bot": with_bot, "with_bot_percent": round(with_bot * 100 / opened) if opened else None}


REASON_GROUPS = (
    (("stars_purchase",), "Покупка Зарников за Stars"), (("quest_reward",), "Награды за квесты"), (("season_reward",), "Награды за сезоны игр"), (("season_pass",), "Награды сезонного пропуска"),
    (("achievement_reward",), "Награды за достижения"), (("chest_v1_reward", "chest_key"), "Сундуки и ключи"),
    (("promocode",), "Промокоды"), (("vip_",), "VIP"), (("pet_",), "Питомцы"),
    (("manual_admin", "bot_admin"), "Выдано и списано из админки"), (("partner_gift", "retirement_"), "Подарки и компенсации"),
    (("cosmetic_", "skin_", "theme_", "global_skin", "showcase_"), "Образы и оформление"), (("shop_",), "Магазин"),
    (("exchange_", "crypto_", "player_coin_", "shadow_relic"), "Биржа"), (("auction_",), "Аукцион"),
)


def reason_title(code: str) -> str:
    for prefixes, title in REASON_GROUPS:
        if any(code == p or code.startswith(p) for p in prefixes):
            return title
    return code


async def economy(db, since_day: date, until_day: date) -> dict:
    """Сколько валюты выдано и потрачено за период и откуда. Переводы между игроками не считаются: сумма у них ноль."""
    from datetime import timezone
    start = _utc_start(since_day).replace(tzinfo=timezone.utc)
    end = _utc_start(until_day + timedelta(days=1)).replace(tzinfo=timezone.utc)
    try:
        rows = await _all(
            db, "SELECT currency, reason_code, COALESCE(SUM(delta) FILTER (WHERE delta > 0), 0), "
                "COALESCE(SUM(-delta) FILTER (WHERE delta < 0), 0) FROM economic_ledger "
                "WHERE created_at >= ? AND created_at < ? GROUP BY currency, reason_code", (start, end))
    except Exception:   # леджера ещё нет (чистая база)
        return {}
    out: dict[str, dict] = {}
    for currency, reason, plus, minus in rows:
        c = out.setdefault(currency, {"issued": 0.0, "spent": 0.0, "transfers": 0.0, "sources": {}, "sinks": {}})
        if reason.startswith("player_transfer_"):
            c["transfers"] += float(plus)
            continue
        title = reason_title(reason)
        c["issued"] += float(plus); c["spent"] += float(minus)
        if plus:
            c["sources"][title] = c["sources"].get(title, 0.0) + float(plus)
        if minus:
            c["sinks"][title] = c["sinks"].get(title, 0.0) + float(minus)
    for c in out.values():
        c["net"] = round(c["issued"] - c["spent"], 2)
        for key in ("issued", "spent", "transfers"):
            c[key] = round(c[key], 2)
        for key in ("sources", "sinks"):
            c[key] = [{"title": t, "amount": round(v, 2)} for t, v in sorted(c[key].items(), key=lambda kv: -kv[1])[:6]]
    return out


async def dashboard(db, days: int) -> dict:
    days = days if days in PERIODS else 1
    until_day = today()
    since_day = until_day - timedelta(days=days - 1)
    site = await _site(db, since_day, until_day)
    bot = await _bot(db, since_day, until_day)
    chats = await _chats(db, since_day, until_day)
    everyone = await _everyone(db, since_day, until_day)
    totals = await _one(db, "SELECT (SELECT COUNT(*) FROM users), (SELECT COUNT(*) FROM chat_settings WHERE chat_id < 0)", ())
    day_list = [(since_day + timedelta(days=i)).isoformat() for i in range(days)]
    prev_until = since_day - timedelta(days=1)
    compare = await _totals(db, prev_until - timedelta(days=days - 1), prev_until)
    return {"days": days, "since": since_day.isoformat(), "until": until_day.isoformat(), "day_list": day_list,
            "everyone": everyone, "players_total": int(totals[0]), "chats_total": int(totals[1]),
            "site": site, "bot": bot, "chats": chats, "compare": compare, "retention": await retention(db),
            "funnel": await funnel(db, since_day, until_day), "economy": await economy(db, since_day, until_day)}


async def export_csv(db, days: int) -> str:
    """Выгрузка за период в CSV (разделитель «;», чтобы открывалось в Excel): по дням, топ команд, топ чатов, экономика."""
    import csv
    import io
    m = await dashboard(db, days)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Период", m["since"], m["until"]])
    w.writerow([])
    w.writerow(["Дата", "Посетителей мини-приложения", "Время в приложении, с", "Людей с командами", "Команд", "Сообщений в чатах", "Писали в чатах"])
    for d in m["day_list"]:
        site, bot, chat = m["site"]["daily"].get(d, {}), m["bot"]["daily"].get(d, {}), m["chats"]["daily"].get(d, {})
        w.writerow([d, site.get("users", 0), site.get("seconds", 0), bot.get("users", 0), bot.get("commands", 0),
                    chat.get("messages", 0), chat.get("users", 0)])
    w.writerow([])
    w.writerow(["Команда", "В чатах", "В личке", "Всего"])
    for x in m["bot"]["top"]:
        w.writerow([f"бот {x['command']}", x["group"], x["private"], x["total"]])
    w.writerow([])
    w.writerow(["Чат", "Сообщений", "Писали"])
    for x in m["chats"]["top"]:
        w.writerow([x["title"], x["messages"], x["users"]])
    w.writerow([])
    w.writerow(["Воронка мини-приложения", "Людей", "От открывших, %", "От прошлого шага, %"])
    for step in m["funnel"]["steps"]:
        w.writerow([step["title"], "" if step["users"] is None else step["users"],
                    "" if step["of_first"] is None else step["of_first"], "" if step["of_prev"] is None else step["of_prev"]])
    w.writerow([])
    w.writerow(["Валюта", "Выдано", "Потрачено", "Итого"])
    for currency, c in m["economy"].items():
        w.writerow([currency, c["issued"], c["spent"], c["net"]])
    return buf.getvalue()
