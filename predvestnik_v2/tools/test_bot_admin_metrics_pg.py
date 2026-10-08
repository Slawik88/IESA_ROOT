"""Админка: метрики — мини-приложение, команды бота, чаты.

Запуск: python tools/test_bot_admin_metrics_pg.py --dsn postgresql://... (пустая тестовая БД!)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

ap = argparse.ArgumentParser()
ap.add_argument("--dsn", required=True)
dsn = ap.parse_args().dsn
os.environ["DATABASE_URL"] = dsn
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ["DEVELOPER_ID"] = "1001"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import timedelta  # noqa: E402
from types import SimpleNamespace  # noqa: E402

DEV, HELPER, SENIOR, P1, P2, P3 = 1001, 3003, 4004, 2002, 2003, 2004


class FakeBot:
    async def me(self):
        return SimpleNamespace(id=999, username="predvestnik_bot")


class FakeMessage:
    def __init__(self, text, uid, chat=-100):
        self.text, self.caption, self.entities = text, None, []
        self.from_user = SimpleNamespace(id=uid, is_bot=False, username=f"u{uid}", full_name=f"U{uid}",
                                         first_name=f"U{uid}")
        self.chat = SimpleNamespace(id=chat, type="supergroup" if chat < 0 else "private", title="Тест")
        self.reply_to_message = None
        self.replies = []

    async def reply(self, text, **kw):
        self.replies.append(text)

    async def answer(self, text, **kw):
        self.replies.append(text)


class Client:
    def __init__(self, app):
        import httpx
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    def __getattr__(self, method):
        return getattr(self.http, method)


async def run():
    from infrastructure.database import create_pool, get_pool
    from infrastructure.pg_adapter import PGAdapter
    from bot.core.database import init_db
    from bot.chat import registry
    from bot.chat.framework import dispatch
    from bot.chat.schema import ensure_chat_schema
    from bot.chat.tracking import local_now, tz_delta
    from bot.startup_schema import ensure_runtime_schema
    from FastAPI.auth import create_session_token
    import FastAPI.main as main

    await create_pool()
    await init_db()
    await ensure_runtime_schema(get_pool())
    await ensure_chat_schema()
    today = local_now().date()
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        for uid, rank in ((DEV, 0), (HELPER, 3), (SENIOR, 4), (P1, 0), (P2, 0), (P3, 0)):
            await db.execute("INSERT INTO users (user_tg_id, user_tg_username, bot_rank) VALUES (?, ?, ?)",
                             (uid, f"u{uid}", rank))
        await db.execute("INSERT INTO chat_settings (chat_id, chat_title) VALUES (-100, 'Основной чат')")
        # Мини-приложение: сегодня P1 (две вкладки, одна сессия) и P2; три дня назад — P3.
        now_utc = local_now() - tz_delta()
        for uid, tab, sess, secs, ago in ((P1, "profile", "s1", 120, 0), (P1, "arena", "s1", 45, 0),
                                          (P1, "arena/rhythm", "s1", 30, 0), (P2, "profile", "s2", 15, 0),
                                          (P3, "top", "s3", 600, 3)):
            await db.execute("INSERT INTO site_analytics (user_id, tab, session_id, visited_at, duration_sec) "
                             "VALUES (?, ?, ?, ?, ?)", (uid, tab, sess, now_utc - timedelta(days=ago, minutes=1), secs))
        # Чаты: сегодня P1 и P2, неделю назад — P3.
        for uid, n, ago in ((P1, 30, 0), (P2, 10, 0), (P3, 5, 5)):
            await db.execute("INSERT INTO daily_user_stats (user_id, chat_id, date, message_count) VALUES (?, -100, ?, ?)",
                             (uid, (today - timedelta(days=ago)).isoformat(), n))
        # Команды бота: две в группе от P1, одна в личке от P2.
        for text, uid, chat in (("бот стрик", P1, -100), ("бот топ", P1, -100), ("бот баланс", P2, P2),
                                ("бот нетакойкоманды", P2, -100)):
            await dispatch(registry, FakeMessage(text, uid, chat), FakeBot(), db)

    client = Client(main.app)
    h = {uid: {"x-session-token": create_session_token(uid)} for uid in (HELPER, SENIOR)}
    assert (await client.get("/bot-admin/api/metrics", headers=h[HELPER])).status_code == 403
    m = (await client.get("/bot-admin/api/metrics?days=1", headers=h[SENIOR])).json()
    s, b, c = m["site"], m["bot"], m["chats"]
    assert (s["visitors"], s["sessions"], s["visits"], s["seconds"]) == (2, 2, 4, 210), s
    assert s["avg_seconds_per_visitor"] == 105, s
    assert [(p["tab"], p["title"], p["visits"], p["users"]) for p in s["pages"]] == \
        [("profile", "Профиль", 2, 2), ("arena", "Игры", 1, 1)], s["pages"]
    assert s["pages"][0]["avg_seconds"] == 68 and s["subpages"][0]["tab"] == "arena/rhythm", s
    assert (b["commands"], b["commands_group"], b["commands_private"], b["users"]) == (3, 2, 1, 2), b
    assert {x["command"]: x["total"] for x in b["top"]} == {"стрик": 1, "топ": 1, "баланс": 1}, b["top"]
    assert (c["messages"], c["users"], c["chats"]) == (40, 2, 1), c
    assert m["everyone"] == 2 and m["players_total"] == 6 and m["chats_total"] == 1, m
    m = (await client.get("/bot-admin/api/metrics?days=7", headers=h[SENIOR])).json()
    assert m["site"]["visitors"] == 3 and m["chats"]["messages"] == 45 and m["everyone"] == 3, m
    assert len(m["day_list"]) == 7 and m["day_list"][-1] == today.isoformat()
    assert m["site"]["daily"][today.isoformat()]["users"] == 2, m["site"]["daily"]
    assert (await client.get("/bot-admin/api/metrics?days=5", headers=h[SENIOR])).json()["days"] == 1


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run())
    print("OK: bot admin metrics on PostgreSQL")


main()
