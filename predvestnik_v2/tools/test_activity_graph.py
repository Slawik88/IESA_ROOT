"""График активности «бот я / бот кто»: рендер PNG, кривая по дням, кэш, параллельные рендеры, подпись с карточкой (без базы).

Запуск: python tools/test_activity_graph.py
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
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


@asynccontextmanager
async def fake_transaction():
    yield


class FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.connection = SimpleNamespace(transaction=fake_transaction)
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


async def check_caption_flow() -> None:
    """Карточка уходит подписью к графику — одним сообщением; переросла лимит — как раньше, двумя."""
    from types import SimpleNamespace
    from bot.chat import profile

    class PhotoMsg:
        def __init__(self, fail_caption=False):
            self.chat = SimpleNamespace(id=-100, type="supergroup")
            self.fail_caption = fail_caption
            self.photos, self.replies = [], []

        async def answer_photo(self, photo, **kw):
            if kw.get("caption") and self.fail_caption:
                raise RuntimeError("Telegram не принял подпись")
            self.photos.append(kw)

        async def reply(self, text, **kw):
            self.replies.append(text)

    def make_ctx(msg):
        ctx = SimpleNamespace(message=msg, db=None, user_id=1)
        async def reply(text, **kw):
            msg.replies.append(text)
        ctx.reply = reply
        return ctx

    target = SimpleNamespace(user_id=7, username="t", name="T")
    caption = "<b>карточка</b>"
    orig_card, orig_graph = profile.card, activity_graph.get_graph

    async def fake_card(_db, _chat, _t, _viewer, _group, _look=None):
        return caption

    async def fake_graph(_db, _uid, _chat, theme=None):
        return b"\x89PNG\r\n\x1a\n" + b"0" * 64

    try:
        profile.card, activity_graph.get_graph = fake_card, fake_graph

        # 1. Подпись влезает: одно сообщение — фото с карточкой в подписи.
        ctx = make_ctx(PhotoMsg())
        await profile.send_card(ctx, target, True)
        assert ctx.message.photos and ctx.message.photos[0]["caption"] == caption, ctx.message.photos
        assert ctx.message.photos[0]["parse_mode"] == "HTML", ctx.message.photos
        assert not ctx.message.replies, ctx.message.replies

        # 2. Карточка длиннее лимита подписи: фото без подписи, затем текст.
        long_caption = "😀" * 600        # 1200 единиц UTF-16 — больше 1024
        async def long_card(_db, _chat, _t, _viewer, _group, _look=None):
            return long_caption
        profile.card = long_card
        ctx = make_ctx(PhotoMsg())
        await profile.send_card(ctx, target, True)
        assert ctx.message.photos and "caption" not in ctx.message.photos[0], ctx.message.photos
        assert ctx.message.replies == [long_caption], ctx.message.replies

        # 3. Telegram не принял подпись: откат на фото без подписи + текст.
        profile.card = fake_card
        ctx = make_ctx(PhotoMsg(fail_caption=True))
        await profile.send_card(ctx, target, True)
        assert ctx.message.photos and "caption" not in ctx.message.photos[0], ctx.message.photos
        assert ctx.message.replies == [caption], ctx.message.replies

        # 4. Графика нет вовсе: только текст.
        async def no_graph(_db, _uid, _chat, theme=None):
            return None
        activity_graph.get_graph = no_graph
        ctx = make_ctx(PhotoMsg())
        await profile.send_card(ctx, target, True)
        assert not ctx.message.photos and ctx.message.replies == [caption], (ctx.message.photos, ctx.message.replies)

        # Сама мера длины: теги не считаются, эмодзи считаются двойными.
        assert profile.caption_len(caption) == 8, profile.caption_len(caption)
        assert profile.caption_len("a" * 1024) == 1024
        assert profile.caption_len("<b>" + "a" * 1024 + "</b>") == 1024
    finally:
        profile.card, activity_graph.get_graph = orig_card, orig_graph


def main() -> None:
    start = local_now().date() - timedelta(days=len(SAMPLE) - 1)
    for theme in activity_graph.THEMES:
        png = activity_graph.render(SAMPLE, start, theme=theme)
        assert png.startswith(b"\x89PNG\r\n\x1a\n") and len(png) > 5000, (theme, len(png))
    default = activity_graph.render(SAMPLE, start)
    assert default.startswith(b"\x89PNG\r\n\x1a\n"), "тема по умолчанию должна рендериться"
    # С историей («динамика» в шапке) и без неё: обе ветки шапки обязаны рендериться.
    for prev in (6.0, None):
        png = activity_graph.render(SAMPLE, start, prev_avg=prev)
        assert png.startswith(b"\x89PNG\r\n\x1a\n"), f"prev_avg={prev}"
    # Лавина первых запросов после суточного промаха кэша: рендеры идут параллельно
    # в потоках — без общего состояния pyplot гонок быть не должно.
    with ThreadPoolExecutor(max_workers=3) as pool:
        racing = list(pool.map(lambda _: activity_graph.render(SAMPLE, start), range(3)))
    assert all(p.startswith(b"\x89PNG\r\n\x1a\n") for p in racing), "параллельный рендер"
    asyncio.run(check_db_logic())
    asyncio.run(check_caption_flow())
    print("OK: activity graph — рендер, дни, кэш, параллельность, подпись с карточкой")


main()
