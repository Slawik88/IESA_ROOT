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

        # Прошлый период и удержание: P1 впервые в чате 10 дней назад, P3 пишет 5 и 4 дня назад (вернулся на следующий день).
        for uid, n, ago in ((P1, 12, 10), (P3, 1, 4)):
            await db.execute("INSERT INTO daily_user_stats (user_id, chat_id, date, message_count) VALUES (?, -100, ?, ?)",
                             (uid, (today - timedelta(days=ago)).isoformat(), n))
        await db.execute("INSERT INTO site_analytics (user_id, tab, session_id, visited_at, duration_sec) VALUES (?, 'profile', 's9', ?, 5)",
                         (P1, now_utc - timedelta(days=8, minutes=1)))
        # Экономика: выдача из квеста и админки, трата в магазине, перевод между игроками (не должен считаться).
        for i, (uid, cur, delta, reason, ago) in enumerate((
                (P1, "mora", 500, "quest_reward", 0), (P2, "mora", 300, "quest_reward", 0), (P1, "mora", -200, "shop_purchase", 0),
                (P1, "mora", -50, "player_transfer_out", 0), (P2, "mora", 50, "player_transfer_in", 0),
                (P2, "zarniki", 20, "manual_admin_grant", 0), (P3, "mora", 999, "quest_reward", 3))):
            op = f"op-metrics-{i}"
            await db.execute("INSERT INTO economic_operations (id, user_id, idempotency_key, request_fingerprint, reason_code, source_type) "
                             "VALUES (?, ?, ?, 'x', ?, 'test')", (op, uid, op, reason))
            await db.execute("INSERT INTO economic_ledger (operation_id, user_id, currency, delta, balance_before, balance_after, reason_code, created_at) "
                             "VALUES (?, ?, ?, ?, 0, ?, ?, ?)",
                             (op, uid, cur, delta, delta, reason, now_utc.replace(tzinfo=None) - timedelta(days=ago, minutes=1)))

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
    assert m["compare"] == {"everyone": 0, "visitors": 0, "commands": 0, "bot_users": 0, "messages": 0, "chat_users": 0}, m["compare"]
    eco = m["economy"]
    assert eco["mora"]["issued"] == 800 and eco["mora"]["spent"] == 200 and eco["mora"]["net"] == 600, eco   # перевод и старая запись не в счёте
    assert eco["mora"]["transfers"] == 50 and eco["zarniki"]["issued"] == 20, eco
    assert eco["mora"]["sources"][0] == {"title": "Награды за квесты", "amount": 800.0}, eco["mora"]["sources"]
    assert eco["mora"]["sinks"] == [{"title": "Магазин", "amount": 200.0}], eco["mora"]["sinks"]
    assert eco["zarniki"]["sources"] == [{"title": "Выдано и списано из админки", "amount": 20.0}], eco["zarniki"]
    r = m["retention"]
    assert (r["d1"]["cohort"], r["d1"]["returned"], r["d1"]["percent"]) == (2, 1, 50), r   # P1 (10 дней назад) и P3 (5 дней назад)
    assert (r["d7"]["cohort"], r["d7"]["returned"], r["d7"]["percent"]) == (1, 0, 0), r      # только P1, вернулся через 10 дней
    assert r["d30"]["cohort"] == 0 and r["d30"]["percent"] is None, r
    m = (await client.get("/bot-admin/api/metrics?days=7", headers=h[SENIOR])).json()
    assert m["site"]["visitors"] == 3 and m["chats"]["messages"] == 46 and m["everyone"] == 3, m
    assert m["compare"]["visitors"] == 1 and m["compare"]["messages"] == 12 and m["compare"]["chat_users"] == 1 \
        and m["compare"]["everyone"] == 1, m["compare"]
    assert m["economy"]["mora"]["issued"] == 800 + 999, m["economy"]   # за неделю входит и старая выдача
    assert len(m["day_list"]) == 7 and m["day_list"][-1] == today.isoformat()
    assert m["site"]["daily"][today.isoformat()]["users"] == 2, m["site"]["daily"]
    assert (await client.get("/bot-admin/api/metrics?days=5", headers=h[SENIOR])).json()["days"] == 1
    # Выгрузка CSV: BOM для Excel, разделитель «;», те же числа, что на экране; доступ — как у раздела.
    assert (await client.get("/bot-admin/api/metrics/export?days=7", headers=h[HELPER])).status_code == 403
    res = await client.get("/bot-admin/api/metrics/export?days=7", headers=h[SENIOR])
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv"), res.headers
    assert 'attachment; filename="metrics-7d.csv"' in res.headers["content-disposition"]
    body = res.content.decode("utf-8")
    assert body.startswith("\ufeff") and "Посетителей мини-приложения" in body, body[:120]
    assert f"{today.isoformat()};2;" in body and "бот стрик;1;0;1" in body and "Основной чат;" in body, body
    assert "mora;1799.0;200.0;1599.0" in body, body


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run())
    print("OK: bot admin metrics on PostgreSQL")


main()
