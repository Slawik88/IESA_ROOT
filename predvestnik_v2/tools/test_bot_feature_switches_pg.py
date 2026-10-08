"""Выключатели функций (/bot-admin, раздел «Функции»): команды в чатах и части сайта.

Запуск: python tools/test_bot_feature_switches_pg.py --dsn postgresql://... (пустая тестовая БД!)
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
os.environ["SITE_OPEN_TO_PLAYERS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from types import SimpleNamespace  # noqa: E402


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

    async def delete(self):
        pass


class FakeBot:
    async def me(self):
        return SimpleNamespace(id=999, username="predvestnik_bot")

    async def get_chat_administrators(self, chat_id):
        return []

    def __getattr__(self, name):
        async def call(*a, **kw):
            return None
        return call


async def main():
    import httpx
    from infrastructure.database import create_pool, get_pool
    from infrastructure.pg_adapter import PGAdapter
    from bot.core.database import init_db
    from bot.chat.schema import ensure_chat_schema
    from bot.chat import registry, on_message
    from bot.chat.framework import dispatch
    from FastAPI.auth import create_session_token
    import FastAPI.main as web

    await create_pool()
    await init_db()
    await ensure_chat_schema()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url="http://test")
    dev = {"x-session-token": create_session_token(1001)}
    player = {"x-session-token": create_session_token(2002)}

    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        for uid in (1001, 2002):
            await db.execute("INSERT INTO users (user_tg_id, user_tg_username) VALUES (?, ?) ON CONFLICT DO NOTHING",
                             (uid, f"u{uid}"))
        for chat in (-100, -200):
            await db.execute("INSERT INTO chat_settings (chat_id, chat_title) VALUES (?, ?) ON CONFLICT DO NOTHING",
                             (chat, f"Чат {chat}"))

        async def say(text, uid=2002, chat=-100):
            m = FakeMessage(text, uid, chat)
            await dispatch(registry, m, FakeBot(), db)
            return " | ".join(m.replies)

        async def switch(feature, enabled, chat_id=0, reason=""):
            r = await client.post("/bot-admin/api/switches", headers=dev,
                                  json={"feature": feature, "enabled": enabled, "chat_id": chat_id, "reason": reason})
            assert r.status_code == 200, r.text
            return r.json()

        assert (await client.get("/bot-admin/api/switches", headers=player)).status_code == 403
        data = (await client.get("/bot-admin/api/switches", headers=dev)).json()
        assert [g["scope"] for g in data["catalog"]] == ["chat", "site"], data
        keys = {x["key"] for g in data["catalog"] for i in g["items"] for x in [i, *i.get("items", [])]}
        assert {"all", "cmd:перевод", "section:games", "group:warps", "site", "site:rhythm"} <= keys
        assert "cmd:админка" not in keys and "cmd:обнять" not in keys                 # вход в админку не выключается
        r = await client.post("/bot-admin/api/switches", headers=dev, json={"feature": "cmd:нет", "enabled": False})
        assert r.status_code == 400
        r = await client.post("/bot-admin/api/switches", headers=dev,
                              json={"feature": "site:rhythm", "enabled": False, "chat_id": -100})
        assert r.status_code == 400 and "только везде" in r.json()["detail"]

        # Одна команда везде, с причиной.
        before = await say("бот перевод, @u1001 10")
        assert "⛔" not in before, before
        state = await switch("cmd:перевод", False, reason="чиним")
        assert state["global"]["cmd:перевод"]["reason"] == "чиним"
        assert await say("бот перевод, @u1001 10") == "⛔ Сейчас это недоступно: чиним"
        assert await say("бот перевод, @u1001 10", chat=-200) == "⛔ Сейчас это недоступно: чиним"
        await switch("cmd:перевод", True)
        assert "⛔" not in await say("бот перевод, @u1001 10")

        # Раздел в одном чате.
        await switch("section:games", False, chat_id=-100)
        assert "⛔" in await say("бот игры")
        assert "⛔" not in await say("бот игры", chat=-200)
        view = (await client.get("/bot-admin/api/switches?chat_id=-100", headers=dev)).json()
        assert "section:games" in view["state"]["chat"] and view["chat"]["title"] == "Чат -100", view
        await switch("section:games", True, chat_id=-100)

        # Варпы набором: без «бот» — молча, с «бот» — ответ.
        await switch("group:warps", False)
        assert await say("бот обнять, @u1001") == "⛔ Сейчас это недоступно."
        m = FakeMessage("обнять", 2002)
        m.reply_to_message = FakeMessage("привет", 1001)
        await dispatch(registry, m, FakeBot(), db)
        assert m.replies == [], m.replies
        await switch("group:warps", True)

        # Весь бот в чате: молчит, учёт сообщений идёт, «бот админка» отвечает.
        await switch("all", False, chat_id=-100)
        m = FakeMessage("бот топ", 2002)
        await on_message(m, FakeBot(), db)
        assert m.replies == [], m.replies
        async with db.execute("SELECT user_messages_count_all_time FROM user_chat_stats "
                              "WHERE user_tg_id = 2002 AND chat_tg_id = -100") as cur:
            assert (await cur.fetchone())[0] >= 1
        m = FakeMessage("бот админка", 1001)
        await on_message(m, FakeBot(), db)
        assert m.replies and m.replies[0].startswith("🛠"), m.replies
        assert "⛔" not in await say("бот топ", chat=-200)
        await switch("all", True, chat_id=-100)

        # Сайт: область и весь сайт. Админка и вход открыты всегда; разработчик проходит.
        await switch("site:rhythm", False, reason="обновляем Ритм")
        r = await client.get("/rhythm-v2/leaderboard", headers=player)
        assert r.status_code == 503 and r.json()["detail"] == "обновляем Ритм", r.text
        r = await client.get("/rhythm-v2/leaderboard", headers=dev)
        assert r.status_code != 503, r.text
        assert (await client.get("/minesweeper-v2/leaderboard", headers=player)).status_code != 503
        await switch("site:rhythm", True)
        await switch("site", False)
        r = await client.get("/", headers={"accept": "text/html"})
        assert r.status_code == 503 and "Временно закрыто" in r.text
        assert (await client.get("/profile/", headers=player)).status_code == 503
        assert (await client.get("/bot-admin")).status_code == 200
        assert (await client.get("/bot-admin/api/me", headers=dev)).status_code == 200
        await switch("site", True)
        assert (await client.get("/", headers={"accept": "text/html"})).status_code == 200

        # Объявления о достижениях.
        from bot.chat import achievements as ach
        await switch("notice:achievements", False)
        m = FakeMessage("x", 2002)
        await ach.announce(db, m, "@x", [ach.Up(ach.BY_ID["messages"], 3, 0)])
        assert m.replies == []
        await switch("notice:achievements", True)
        await ach.announce(db, m, "@x", [ach.Up(ach.BY_ID["messages"], 3, 0)])
        assert len(m.replies) == 1
        # Настройки: какие валюты переводятся.
        st = (await client.get("/bot-admin/api/settings", headers=dev)).json()
        assert {c["code"]: (c["enabled"], c["locked"]) for c in st["transfer"]} == {
            "mora": (True, False), "diamonds": (True, False), "essence": (False, True), "zarniki": (False, True)}, st
        r = await client.post("/bot-admin/api/settings/transfer", headers=dev, json={"currencies": ["zarniki"]})
        assert r.status_code == 400
        r = await client.post("/bot-admin/api/settings/transfer", headers=dev, json={"currencies": ["mora"]})
        assert [c["code"] for c in r.json()["transfer"] if c["enabled"]] == ["mora"], r.text
        from bot.chat import settings as bot_settings
        assert await bot_settings.transferable(db) == ("mora",)
    print("OK: feature switches for chat commands and the site")


asyncio.run(main())
