"""MET-01: метрики не считают аккаунты команды, и ни один запрос к пяти таблицам не забыл условие.

Без базы: подменный db записывает каждый SQL и его параметры, вызывается весь дашборд, CSV и итоги дня.
Проверяется: 1) каждый запрос к site_analytics, bot_user_daily, daily_user_stats, economic_ledger, users и user_chat_stats несёт
`<> ALL(?::bigint[])` (кроме явного списка исключений); 2) число `?` равно числу параметров, а массив стоит ровно там, где `::bigint[]`;
3) при пустом наборе условий нет вообще (поведение как раньше).

Запуск: python tools/test_bot_metrics_staff_guard.py
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from types import SimpleNamespace

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
os.environ["DEVELOPER_ID"] = "1001"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import bot_metrics, owner_digest  # noqa: E402

GUARDED = ("site_analytics", "bot_user_daily", "daily_user_stats", "economic_ledger", "FROM users", "user_chat_stats")
# Запросы, где фильтра по набору быть не должно или он другого вида (каждый объяснён)
EXEMPT = (
    "bot_rank = ANY",                 # сам набор
    "user_id = ANY(?::bigint[])",     # оборот аккаунтов команды: нужен именно он
    "FROM bot_reports",               # жалобы в дайджесте, не метрика людей
    "bot_left_at IS NULL",            # bot_health.counters: состояние чатов («удалили бота», «без прав»), не активность людей
    "dm_blocked_at IS NOT NULL",      # bot_health.counters: сколько игроков заблокировали бота (рассылка), это состояние базы
)


def columns(sql: str) -> int:
    """Сколько колонок в верхнем SELECT (скобки и CTE пропускаются): подменный fetchone отдаёт кортеж нужной длины."""
    depth, starts = 0, []
    for i, ch in enumerate(sql):
        depth += ch == "("
        depth -= ch == ")"
        if depth == 0 and sql[i:i + 7].upper() == "SELECT ":
            starts.append(i + 7)
    start, depth, n = starts[-1], 0, 1
    for i in range(start, len(sql)):
        ch = sql[i]
        depth += ch == "("
        depth -= ch == ")"
        if depth == 0 and sql[i:i + 6].upper() == " FROM ":
            break
        if depth == 0 and ch == ",":
            n += 1
    return n


class Cursor:
    def __init__(self, sql):
        self.sql = sql

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def fetchone(self):
        return tuple(0 for _ in range(columns(self.sql)))

    async def fetchall(self):
        if "bot_rank = ANY" in self.sql:
            return [(5005,), (6006,)]
        return []


class FakeDb:
    def __init__(self):
        self.log = []

    def execute(self, sql, args=()):
        self.log.append((sql, tuple(args)))
        return Cursor(sql)


def check(log, expect_filter):
    bad = []
    for sql, args in log:
        marks = re.findall(r"\?(::[a-z0-9]+\[\])?", sql)
        if len(marks) != len(args):
            bad.append(f"число ? ({len(marks)}) не равно числу параметров ({len(args)}): {sql[:90]}")
            continue
        for m, a in zip(marks, args):
            if bool(m) != isinstance(a, list):
                bad.append(f"массив стоит не на месте массива: {sql[:90]}")
                break
        if any(e in sql for e in EXEMPT) or not any(g in sql for g in GUARDED):
            continue
        has = "<> ALL(?::bigint[])" in sql
        if expect_filter and not has:
            bad.append(f"нет условия исключения: {sql[:110]}")
        if not expect_filter and has:
            bad.append(f"условие есть при пустом наборе: {sql[:110]}")
    return bad


async def run(db_rows_staff: bool):
    db = FakeDb()
    if not db_rows_staff:
        bot_metrics.config = SimpleNamespace(developer_id=0)   # конфиг заморожен: подменяем целиком
        orig = Cursor.fetchall

        async def none(self):
            return [] if "bot_rank = ANY" in self.sql else await orig(self)
        Cursor.fetchall = none
    bot_metrics._retention_cache = None
    await bot_metrics.dashboard(db, 7)
    await bot_metrics.export_csv(db, 1)
    bot_metrics._retention_cache = None
    try:
        await owner_digest.build(db)
    except Exception:
        pass   # дайджест тянет bot_health и ошибки лога: нас интересуют только его запросы
    return db.log


def main() -> int:
    bad = []
    log = asyncio.run(run(True))
    n = len([1 for sql, _ in log if any(g in sql for g in GUARDED)])
    assert n >= 15, f"запросов к таблицам метрик слишком мало ({n}): тест перестал видеть дашборд"
    bad += check(log, True)
    ids = [a for sql, args in log if "<> ALL" in sql for a in args if isinstance(a, list)]
    assert ids and all(i == [1001, 5005, 6006] for i in ids), ids
    bad += check(asyncio.run(run(False)), False)
    for line in bad:
        print("✗", line)
    if not bad:
        print(f"OK: все {n} запросов к таблицам метрик несут исключение команды; пустой набор без условий")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
