"""Метрики для админки: мини-приложение, команды бота, активность в чатах.

Сайт — существующая таблица site_analytics (мини-приложение само шлёт открытия вкладок
и время на них). Команды бота — новые суточные счётчики bot_command_daily и bot_user_daily
(пишутся при каждой выполненной команде). Чаты — существующая daily_user_stats.
Сутки — по местному времени бота (TIMEZONE_OFFSET), как у топов и стрика.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from bot.chat.tracking import local_now, tz_delta
from bot.config import config

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
# Кто не входит в статистику: разработчик (DEVELOPER_ID) и роли «Разработчик» и «Создатель» из bot/chat/global_ranks.py.
# Ранг 1 «Тестер» сюда не входит: если тестеры только служебные аккаунты, добавьте 1 (решение владельца).
STAFF_RANKS = (5, 6)


class Staff:
    """Аккаунты команды, которых метрики пропускают. Один набор на вызов; пустой набор не добавляет условий (как раньше)."""

    def __init__(self, ids=()):
        self.ids = sorted({int(i) for i in ids})
        self.args = (self.ids,) if self.ids else ()

    def sql(self, col: str) -> str:
        # `<> ALL`, а не `NOT IN (…)`: один параметр-массив, на пустом наборе условие просто не пишется.
        # user_id во всех пяти таблицах NOT NULL, поэтому NULL-ловушки нет.
        return f" AND {col} <> ALL(?::bigint[])" if self.ids else ""

    def __len__(self) -> int:
        return len(self.ids)


async def staff_ids(db) -> Staff:
    rows = await _all(db, "SELECT user_tg_id FROM users WHERE bot_rank = ANY(?::int[])", (list(STAFF_RANKS),))
    ids = {int(r[0]) for r in rows}
    if config.developer_id:
        ids.add(int(config.developer_id))
    return Staff(ids)


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


async def _site(db, since_day: date, until_day: date, staff: Staff | None = None) -> dict:
    staff = staff or await staff_ids(db)
    start, end = _utc_start(since_day), _utc_start(until_day + timedelta(days=1))
    span = "visited_at >= ? AND visited_at < ?" + staff.sql("user_id")
    row = await _one(db, f"SELECT COUNT(DISTINCT user_id), COUNT(DISTINCT session_id), COUNT(*), "
                         f"COALESCE(SUM(duration_sec), 0) FROM site_analytics WHERE {span}", (start, end, *staff.args))
    visitors, sessions, visits, seconds = (int(x) for x in row)
    rows = await _all(db, f"SELECT tab, COUNT(*), COUNT(DISTINCT user_id), COALESCE(SUM(duration_sec), 0) "
                          f"FROM site_analytics WHERE {span} GROUP BY tab ORDER BY 2 DESC LIMIT 60", (start, end, *staff.args))
    pages, subpages = [], []
    for tab, n, users, secs in rows:
        item = {"tab": tab, "title": PAGE_TITLES.get(tab, tab), "visits": int(n), "users": int(users),
                "seconds": int(secs), "avg_seconds": round(int(secs) / int(n)) if n else 0}
        (subpages if "/" in tab else pages).append(item)
    shift = int(tz_delta().total_seconds())
    daily = await _all(db, f"SELECT (visited_at + (? * INTERVAL '1 second'))::date AS d, COUNT(DISTINCT user_id), "
                           f"COALESCE(SUM(duration_sec), 0) FROM site_analytics WHERE {span} GROUP BY d ORDER BY d",
                       (shift, start, end, *staff.args))
    return {"visitors": visitors, "sessions": sessions, "visits": visits, "seconds": seconds,
            "avg_seconds_per_visitor": round(seconds / visitors) if visitors else 0,
            "pages": pages, "subpages": subpages[:20],
            "daily": {str(d): {"users": int(u), "seconds": int(s)} for d, u, s in daily}}


async def _bot(db, since_day: date, until_day: date, staff: Staff | None = None) -> dict:
    """Команды и люди считаются из bot_user_daily (там есть user_id, команда команды не попадёт в итог).
    «Топ команд» берётся из bot_command_daily: в ней нет user_id, поэтому задним числом её не очистить."""
    staff = staff or await staff_ids(db)
    span = "day BETWEEN ? AND ?"
    users_span = span + staff.sql("user_id")
    args = (since_day, until_day)
    uargs = (*args, *staff.args)
    cmds = {r[0]: int(r[1]) for r in await _all(
        db, f"SELECT place, COALESCE(SUM(commands), 0) FROM bot_user_daily WHERE {users_span} GROUP BY place", uargs)}
    users = {r[0]: int(r[1]) for r in await _all(
        db, f"SELECT place, COUNT(DISTINCT user_id) FROM bot_user_daily WHERE {users_span} GROUP BY place", uargs)}
    total_users = int((await _one(db, f"SELECT COUNT(DISTINCT user_id) FROM bot_user_daily WHERE {users_span}", uargs))[0])
    top = await _all(db, f"SELECT command, SUM(uses) FILTER (WHERE place = 'group'), "
                         f"SUM(uses) FILTER (WHERE place = 'private'), SUM(uses) FROM bot_command_daily "
                         f"WHERE {span} GROUP BY command ORDER BY 4 DESC LIMIT 20", args)
    daily = await _all(db, f"SELECT day, COUNT(DISTINCT user_id), SUM(commands) FROM bot_user_daily "
                           f"WHERE {users_span} GROUP BY day ORDER BY day", uargs)
    return {"commands": sum(cmds.values()), "commands_group": cmds.get("group", 0),
            "commands_private": cmds.get("private", 0), "users": total_users,
            "users_group": users.get("group", 0), "users_private": users.get("private", 0),
            "top": [{"command": c, "group": int(g or 0), "private": int(p or 0), "total": int(t)} for c, g, p, t in top],
            "top_includes_staff": bool(staff),
            "daily": {str(d): {"users": int(u), "commands": int(n)} for d, u, n in daily}}


async def _chats(db, since_day: date, until_day: date, staff: Staff | None = None) -> dict:
    staff = staff or await staff_ids(db)
    args = (since_day.isoformat(), until_day.isoformat(), *staff.args)
    span = "date BETWEEN ? AND ?"
    row = await _one(db, f"SELECT COALESCE(SUM(message_count), 0), COUNT(DISTINCT user_id), COUNT(DISTINCT chat_id) "
                         f"FROM daily_user_stats WHERE {span} AND chat_id < 0{staff.sql('user_id')}", args)
    top = await _all(db, f"SELECT d.chat_id, c.chat_title, SUM(d.message_count), COUNT(DISTINCT d.user_id) "
                         f"FROM daily_user_stats d LEFT JOIN chat_settings c ON c.chat_id = d.chat_id "
                         f"WHERE d.{span} AND d.chat_id < 0{staff.sql('d.user_id')} GROUP BY d.chat_id, c.chat_title ORDER BY 3 DESC LIMIT 10", args)
    daily = await _all(db, f"SELECT date, SUM(message_count), COUNT(DISTINCT user_id) FROM daily_user_stats "
                           f"WHERE {span} AND chat_id < 0{staff.sql('user_id')} GROUP BY date ORDER BY date", args)
    return {"messages": int(row[0]), "users": int(row[1]), "chats": int(row[2]),
            "top": [{"id": int(i), "title": t or str(i), "messages": int(m), "users": int(u)} for i, t, m, u in top],
            "daily": {str(d): {"messages": int(m), "users": int(u)} for d, m, u in daily}}


async def _everyone(db, since_day: date, until_day: date, staff: Staff | None = None) -> int:
    """Уникальные люди хоть где-то: сайт, команды бота, сообщения в чатах."""
    staff = staff or await staff_ids(db)
    start, end = _utc_start(since_day), _utc_start(until_day + timedelta(days=1))
    return int((await _one(
        db, f"SELECT COUNT(*) FROM (SELECT user_id FROM site_analytics WHERE visited_at >= ? AND visited_at < ?{staff.sql('user_id')} "
            f"UNION SELECT user_id FROM bot_user_daily WHERE day BETWEEN ? AND ?{staff.sql('user_id')} "
            f"UNION SELECT user_id FROM daily_user_stats WHERE date BETWEEN ? AND ? AND chat_id < 0{staff.sql('user_id')}) x",
        (start, end, *staff.args, since_day, until_day, *staff.args, since_day.isoformat(), until_day.isoformat(), *staff.args)))[0])


async def _totals(db, since_day: date, until_day: date, staff: Staff | None = None) -> dict:
    """Главные числа периода: для сравнения с предыдущим таким же."""
    staff = staff or await staff_ids(db)
    start, end = _utc_start(since_day), _utc_start(until_day + timedelta(days=1))
    visitors = int((await _one(db, f"SELECT COUNT(DISTINCT user_id) FROM site_analytics WHERE visited_at >= ? AND visited_at < ?{staff.sql('user_id')}",
                               (start, end, *staff.args)))[0])
    commands, bot_users = await _one(db, f"SELECT COALESCE(SUM(commands), 0), COUNT(DISTINCT user_id) FROM bot_user_daily "
                                         f"WHERE day BETWEEN ? AND ?{staff.sql('user_id')}", (since_day, until_day, *staff.args))
    messages, chat_users = await _one(db, f"SELECT COALESCE(SUM(message_count), 0), COUNT(DISTINCT user_id) FROM daily_user_stats "
                                          f"WHERE date BETWEEN ? AND ? AND chat_id < 0{staff.sql('user_id')}",
                                      (since_day.isoformat(), until_day.isoformat(), *staff.args))
    return {"everyone": await _everyone(db, since_day, until_day, staff), "visitors": visitors, "commands": int(commands),
            "bot_users": int(bot_users), "messages": int(messages), "chat_users": int(chat_users)}


_retention_cache: tuple[float, date, dict] | None = None
RETENTION_TTL = 600.0


async def retention(db, staff: Staff | None = None) -> dict:
    """Удержание: какая доля новых людей вернулась на следующий день, в течение 7 и 30 дней.

    «Новый» — впервые замечен в сообщениях чатов или командах бота. Для каждого окна берётся своя когорта, чтобы у всех
    уже прошёл нужный срок. Запрос тяжёлый, поэтому ответ держится десять минут."""
    import time as _time
    global _retention_cache
    day = today()
    staff = staff or await staff_ids(db)
    if _retention_cache and _time.time() - _retention_cache[0] < RETENTION_TTL and _retention_cache[1] == day:
        return _retention_cache[2]
    act = (f"SELECT user_id, date::date AS d FROM daily_user_stats WHERE chat_id < 0 AND date ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'{staff.sql('user_id')} "
           f"UNION SELECT user_id, day AS d FROM bot_user_daily WHERE TRUE{staff.sql('user_id')}")
    windows = (("d1", 1, 30, 1), ("d7", 7, 37, 7), ("d30", 30, 60, 30))
    parts, args = [], [*staff.args, *staff.args]   # по одному массиву на каждую ветку act
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


async def funnel(db, since_day: date, until_day: date, staff: Staff | None = None) -> dict:
    """Воронка мини-приложения за период: открыл → заглянул в два раздела → провёл минуту → потратил валюту.

    Каждый шаг входит в предыдущий (это те же люди, которые прошли дальше), поэтому проценты читаются как «сколько дошло».
    Отдельно: сколько из открывших приложение пользуются и командами бота. Журнала валюты может ещё не быть — тогда
    последний шаг пустой, а остальные считаются."""
    from datetime import timezone
    staff = staff or await staff_ids(db)
    start, end = _utc_start(since_day), _utc_start(until_day + timedelta(days=1))
    row = await _one(
        db, f"WITH v AS (SELECT user_id, COUNT(DISTINCT tab) AS tabs, COALESCE(SUM(duration_sec), 0) AS secs FROM site_analytics "
            f"WHERE visited_at >= ? AND visited_at < ?{staff.sql('user_id')} GROUP BY user_id) "
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE tabs >= ?), COUNT(*) FILTER (WHERE tabs >= ? AND secs >= ?), "
            "COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM bot_user_daily b WHERE b.user_id = v.user_id AND b.day BETWEEN ? AND ?)) FROM v",
        (start, end, *staff.args, FUNNEL_MIN_TABS, FUNNEL_MIN_TABS, FUNNEL_MIN_SECONDS, since_day, until_day))
    opened, deeper, stayed, with_bot = (int(x) for x in row)
    spent = None
    try:
        spent = int((await _one(
            db, f"WITH v AS (SELECT user_id FROM site_analytics WHERE visited_at >= ? AND visited_at < ?{staff.sql('user_id')} GROUP BY user_id "
                f"HAVING COUNT(DISTINCT tab) >= ? AND COALESCE(SUM(duration_sec), 0) >= ?) "
                "SELECT COUNT(*) FROM v WHERE EXISTS (SELECT 1 FROM economic_ledger l WHERE l.user_id = v.user_id "
                "AND l.delta < 0 AND l.created_at >= ? AND l.created_at < ?)",
            (start, end, *staff.args, FUNNEL_MIN_TABS, FUNNEL_MIN_SECONDS, start.replace(tzinfo=timezone.utc), end.replace(tzinfo=timezone.utc))))[0])
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


async def economy(db, since_day: date, until_day: date, staff: Staff | None = None) -> dict:
    """Сколько валюты выдано и потрачено за период и откуда. Переводы между игроками не считаются: сумма у них ноль.

    Аккаунты команды в основной счёт не входят; их обороты отдельно в ключе «_staff», чтобы выпуск валюты не терялся."""
    from datetime import timezone
    staff = staff or await staff_ids(db)
    start = _utc_start(since_day).replace(tzinfo=timezone.utc)
    end = _utc_start(until_day + timedelta(days=1)).replace(tzinfo=timezone.utc)
    try:
        rows = await _all(
            db, "SELECT currency, reason_code, COALESCE(SUM(delta) FILTER (WHERE delta > 0), 0), "
                f"COALESCE(SUM(-delta) FILTER (WHERE delta < 0), 0) FROM economic_ledger "
                f"WHERE created_at >= ? AND created_at < ?{staff.sql('user_id')} GROUP BY currency, reason_code", (start, end, *staff.args))
        staff_rows = await _all(
            db, "SELECT currency, COALESCE(SUM(delta) FILTER (WHERE delta > 0), 0), COALESCE(SUM(-delta) FILTER (WHERE delta < 0), 0) "
                "FROM economic_ledger WHERE created_at >= ? AND created_at < ? AND user_id = ANY(?::bigint[]) GROUP BY currency",
            (start, end, staff.ids)) if staff else []
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
    out["_staff"] = {cur: {"issued": round(float(p), 2), "spent": round(float(m), 2)} for cur, p, m in staff_rows if p or m}
    return out


async def dashboard(db, days: int) -> dict:
    days = days if days in PERIODS else 1
    until_day = today()
    since_day = until_day - timedelta(days=days - 1)
    staff = await staff_ids(db)   # один набор на весь ответ
    site = await _site(db, since_day, until_day, staff)
    bot = await _bot(db, since_day, until_day, staff)
    chats = await _chats(db, since_day, until_day, staff)
    everyone = await _everyone(db, since_day, until_day, staff)
    totals = await _one(db, f"SELECT (SELECT COUNT(*) FROM users WHERE TRUE{staff.sql('user_tg_id')}), "
                            f"(SELECT COUNT(*) FROM chat_settings WHERE chat_id < 0)", staff.args)
    day_list = [(since_day + timedelta(days=i)).isoformat() for i in range(days)]
    prev_until = since_day - timedelta(days=1)
    compare = await _totals(db, prev_until - timedelta(days=days - 1), prev_until, staff)
    return {"days": days, "since": since_day.isoformat(), "until": until_day.isoformat(), "day_list": day_list,
            "everyone": everyone, "players_total": int(totals[0]), "chats_total": int(totals[1]),
            "site": site, "bot": bot, "chats": chats, "compare": compare, "retention": await retention(db, staff),
            "funnel": await funnel(db, since_day, until_day, staff), "economy": await economy(db, since_day, until_day, staff),
            "excluded": len(staff)}


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
        if currency != "_staff":
            w.writerow([currency, c["issued"], c["spent"], c["net"]])
    for currency, c in m["economy"].get("_staff", {}).items():
        w.writerow([f"{currency} (аккаунты команды)", c["issued"], c["spent"], round(c["issued"] - c["spent"], 2)])
    w.writerow([])
    w.writerow(["Без аккаунтов команды", m["excluded"]])
    w.writerow(["«Топ команд» включает команды аккаунтов команды" if m["bot"]["top_includes_staff"] else "«Топ команд» без оговорок"])
    return buf.getvalue()
