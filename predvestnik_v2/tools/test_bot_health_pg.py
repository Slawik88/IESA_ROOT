"""Админка: вкладка «Состояние» и ежедневный отчёт владельцу.

Запуск: python tools/test_bot_health_pg.py --dsn postgresql://... (пустая тестовая БД!)
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

from datetime import datetime, time, timedelta  # noqa: E402
from types import SimpleNamespace  # noqa: E402

DEV, HELPER, SENIOR, P1, P2 = 1001, 3003, 4004, 2002, 2003


class FakeBot:
    def __init__(self):
        self.sent = []

    async def me(self):
        return SimpleNamespace(id=999, username="predvestnik_bot")

    async def send_message(self, chat_id, text, **kw):
        if chat_id == HELPER:
            raise RuntimeError("Forbidden: bot can't initiate conversation")
        self.sent.append((chat_id, text))


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
    from bot.chat.schema import ensure_chat_schema
    from bot.chat.tracking import local_now, tz_delta
    from bot.startup_schema import ensure_runtime_schema
    from FastAPI.auth import create_session_token
    from FastAPI.routers.bot_admin import people
    from loguru import logger
    from services import bot_health, bot_metrics, broadcasts, owner_digest
    import FastAPI.main as main

    await create_pool()
    await init_db()
    await ensure_runtime_schema(get_pool())
    await ensure_chat_schema()
    bot = FakeBot()
    people.set_bot(bot)
    yesterday = local_now().date() - timedelta(days=1)
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        for uid, rank in ((DEV, 0), (HELPER, 3), (SENIOR, 4), (P1, 0), (P2, 0)):
            await db.execute("INSERT INTO users (user_tg_id, user_tg_username, bot_rank) VALUES (?, ?, ?)", (uid, f"u{uid}", rank))
        await db.execute("UPDATE users SET dm_blocked_at = NOW() WHERE user_tg_id = ?", (P2,))
        await db.execute("INSERT INTO chat_settings (chat_id, chat_title, bot_can_moderate) VALUES (-100, 'Рабочий', TRUE)")
        await db.execute("INSERT INTO chat_settings (chat_id, chat_title, bot_can_moderate) VALUES (-200, 'Без прав', FALSE)")
        await db.execute("INSERT INTO chat_settings (chat_id, chat_title, bot_left_at) VALUES (-300, 'Удалили', NOW())")
        await db.execute("INSERT INTO chat_settings (chat_id, chat_title) VALUES (-400, 'Тихий')")
        joined = datetime.combine(yesterday, time(12, 0)) - tz_delta()
        await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, joined_at) VALUES (?, -100, ?)", (P1, joined))
        for chat in (-100, -200):
            await db.execute("INSERT INTO daily_user_stats (user_id, chat_id, date, message_count) VALUES (?, ?, ?, 40)",
                             (P1, chat, local_now().date().isoformat()))
        await db.execute("INSERT INTO daily_user_stats (user_id, chat_id, date, message_count) VALUES (?, -100, ?, 40)",
                         (P1, yesterday.isoformat()))
        await db.execute("INSERT INTO bot_reports (chat_id, target_id, reporter_id, reason) VALUES (-100, ?, ?, 'флуд')", (P2, P1))

    client = Client(main.app)
    h = {u: {"x-session-token": create_session_token(u)} for u in (DEV, HELPER, SENIOR)}
    api = "/bot-admin/api/health"

    assert (await client.get(api, headers=h[HELPER])).status_code == 403
    logger.error("boom из теста")
    r = await client.get(api, headers=h[SENIOR])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["telegram"]["ok"] and d["telegram"]["username"] == "predvestnik_bot", d["telegram"]
    assert d["process"]["uptime_seconds"] >= 0 and d["database"]["ms"] >= 0 and d["process"]["python"]
    assert d["errors"]["count_24h"] >= 1 and d["errors"]["recent"][0]["text"] == "boom из теста", d["errors"]
    assert d["chats"] == {"active": 3, "left": 1, "no_rights": 1, "quiet": 1}, d["chats"]    # тихий только -400
    assert d["players"] == {"total": 5, "blocked_bot": 1}, d["players"]
    assert d["queues"] == {"broadcasts_running": 0, "broadcasts_scheduled": 0, "reports_open": 1}, d["queues"]
    assert d["digest"]["enabled"] is True and d["digest"]["hour"] == 9 and d["digest"]["can_edit"] is False
    assert (await client.get(api, headers=h[DEV])).json()["digest"]["can_edit"] is True

    # настройка отчёта: только владелец
    assert (await client.post(f"{api}/digest", headers=h[SENIOR], json={"enabled": False, "hour": 7})).status_code == 403
    assert (await client.post(f"{api}/digest", headers=h[DEV], json={"enabled": True, "hour": 30})).status_code == 400
    assert (await client.post(f"{api}/digest", headers=h[DEV], json={"enabled": True, "hour": "x"})).status_code == 400
    r = await client.post(f"{api}/digest", headers=h[DEV], json={"enabled": False, "hour": 7})
    assert r.status_code == 200 and r.json()["digest"]["hour"] == 7 and r.json()["digest"]["enabled"] is False, r.text
    assert (await client.get(api, headers=h[SENIOR])).json()["digest"] == {"enabled": False, "hour": 7, "can_edit": False}

    # текст отчёта за вчера
    async with get_pool().acquire() as conn:
        text = await owner_digest.build(PGAdapter(conn))
    assert "Итоги дня" in text and yesterday.strftime("%d.%m.%Y") in text, text
    assert "Новых игроков: <b>1</b>" in text and "Сообщений в чатах: <b>40</b>" in text, text
    assert "Открытых жалоб: <b>1</b>" in text and "Бота удалили из чатов: 1" in text and "Без прав модерации: 1" in text, text
    # «Прислать мне»: уходит тому, кто нажал; закрытая личка — понятная ошибка
    bot.sent.clear()
    r = await client.post(f"{api}/digest/test", headers=h[SENIOR])
    assert r.status_code == 200 and bot.sent[0][0] == SENIOR and "Итоги дня" in bot.sent[0][1], (r.text, bot.sent)
    assert (await client.post(f"{api}/digest/test", headers=h[HELPER])).status_code == 403

    # планировщик: раз в сутки, только если включён и час наступил
    pool_db = broadcasts.pool_db_factory()
    bot.sent.clear()
    assert await owner_digest.send_if_due(bot, pool_db) is False and not bot.sent      # выключен
    await client.post(f"{api}/digest", headers=h[DEV], json={"enabled": True, "hour": 0})
    assert await owner_digest.send_if_due(bot, pool_db) is True
    assert [x[0] for x in bot.sent] == [DEV] and "Итоги дня" in bot.sent[0][1], bot.sent
    assert await owner_digest.send_if_due(bot, pool_db) is False and len(bot.sent) == 1  # за сегодня уже отправлено
    feed = (await client.get("/bot-admin/api/journal?days=1", headers=h[DEV])).json()
    assert "Ежедневный отчёт владельцу" in {x["title"] for x in feed["items"]}, [x["title"] for x in feed["items"]]
    # сбой отправки не повторяется каждую минуту
    async with get_pool().acquire() as conn:
        await PGAdapter(conn).execute("DELETE FROM bot_settings WHERE key = 'owner_digest_state'")
    class Broken(FakeBot):
        async def send_message(self, *a, **kw):
            raise RuntimeError("down")
    assert await owner_digest.send_if_due(Broken(), pool_db) is False
    assert await owner_digest.send_if_due(bot, pool_db) is False


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run())
    print("OK: bot health and owner digest on PostgreSQL")


main()
