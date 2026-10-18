"""График активности «бот я / бот кто»: рендер PNG, кривая по дням, кэш, параллельные рендеры (без базы).

Запуск: python tools/test_activity_graph.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot.chat import activity_graph            # noqa: E402
from bot.chat.tracking import local_now        # noqa: E402

SAMPLE = [0, 5, 12, 3, 0, 8, 40, 2, 1, 7, 15, 22, 0, 0, 3, 9, 11, 6, 2, 0, 4, 18, 25, 7, 3, 1, 0, 12, 9, 5]


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    async def fetchall(self):
        return self._rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.calls: list[tuple] = []

    def execute(self, sql, args=()):
        self.calls.append((sql, args))
        return FakeCursor(self.rows)


async def check_db_logic() -> None:
    today = local_now().date()
    rows = [((today - timedelta(days=2)).isoformat(), 5), (today.isoformat(), 3)]
    db = FakeDB(rows)
    start, counts = await activity_graph.daily_counts(db, 42, -100, days=5)
    assert start == today - timedelta(days=4), start
    assert counts == [0, 0, 5, 0, 3], counts

    # Повторный запрос в тот же день — из кэша, без SQL.
    db2 = FakeDB([(today.isoformat(), 4)])
    png1 = await activity_graph.get_graph(db2, 777, None, days=3)
    png2 = await activity_graph.get_graph(db2, 777, None, days=3)
    assert png1 and png1 == png2 and len(db2.calls) == 1, (png1, len(db2.calls))

    # Ни одного сообщения в окне — графика нет, карточка покажется без него.
    assert await activity_graph.get_graph(FakeDB([]), 778, None, days=3) is None


def main() -> None:
    start = local_now().date() - timedelta(days=len(SAMPLE) - 1)
    for theme in activity_graph.THEMES:
        png = activity_graph.render(SAMPLE, start, theme=theme)
        assert png.startswith(b"\x89PNG\r\n\x1a\n") and len(png) > 5000, (theme, len(png))
    default = activity_graph.render(SAMPLE, start)
    assert default.startswith(b"\x89PNG\r\n\x1a\n"), "тема по умолчанию должна рендериться"
    # Лавина первых запросов после суточного промаха кэша: рендеры идут параллельно
    # в потоках — без общего состояния pyplot гонок быть не должно.
    with ThreadPoolExecutor(max_workers=3) as pool:
        racing = list(pool.map(lambda _: activity_graph.render(SAMPLE, start), range(3)))
    assert all(p.startswith(b"\x89PNG\r\n\x1a\n") for p in racing), "параллельный рендер"
    asyncio.run(check_db_logic())
    print("OK: activity graph — рендер, дни, кэш, параллельность")


main()
