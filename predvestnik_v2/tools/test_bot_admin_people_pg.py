"""Админка: поиск игроков и чатов, карточки, действия персонала и глобальная модерация.

Запуск: python tools/test_bot_admin_people_pg.py --dsn postgresql://... (пустая тестовая БД!)
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

from types import SimpleNamespace  # noqa: E402

DEV, HELPER, SENIOR, CODER, P1, P2 = 1001, 3003, 4004, 5005, 2002, 2003


class FakeBot:
    """Записывает вызовы Bot API; в чате -200 у бота нет прав."""
    def __init__(self):
        self.calls = []

    async def me(self):
        return SimpleNamespace(id=999, username="predvestnik_bot")

    def _call(self, name, chat_id, *args):
        self.calls.append((name, chat_id, *args))
        if chat_id == -200:
            raise RuntimeError("Bad Request: not enough rights to restrict/unrestrict chat member")

    async def ban_chat_member(self, chat_id, user_id, until_date=None):
        self._call("ban", chat_id, user_id)

    async def unban_chat_member(self, chat_id, user_id, only_if_banned=False):
        self._call("unban", chat_id, user_id)

    async def restrict_chat_member(self, chat_id, user_id, permissions=None, until_date=None):
        self._call("restrict", chat_id, user_id)

    async def get_chat(self, chat_id):
        return SimpleNamespace(permissions=None)

    async def send_message(self, chat_id, text, **kw):
        self._call("send", chat_id, text)

    async def leave_chat(self, chat_id):
        self._call("leave", chat_id)


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


async def prepare():
    from infrastructure.database import create_pool, get_pool
    from infrastructure.pg_adapter import PGAdapter
    from bot.core.database import init_db
    from bot.chat.schema import ensure_chat_schema
    from bot.chat.tracking import local_now
    from bot.startup_schema import ensure_runtime_schema
    await create_pool()
    await init_db()
    await ensure_runtime_schema(get_pool())
    await ensure_chat_schema()
    await ensure_chat_schema()   # повторный запуск безопасен
    today = local_now().date().isoformat()
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        for uid, rank in ((DEV, 0), (HELPER, 3), (SENIOR, 4), (CODER, 5), (P1, 0), (P2, 0)):
            await db.execute("INSERT INTO users (user_tg_id, user_tg_username, bot_rank) VALUES (?, ?, ?) "
                             "ON CONFLICT DO NOTHING", (uid, f"u{uid}", rank))
        for chat, title in ((-100, "Основной чат"), (-200, "Другой чат"), (-300, "Новый чат")):
            await db.execute("INSERT INTO chat_settings (chat_id, chat_title) VALUES (?, ?) ON CONFLICT DO NOTHING",
                             (chat, title))
        for uid, chat, n in ((P1, -100, 120), (P2, -100, 40), (P1, -200, 5), (CODER, -100, 7)):
            await db.execute(
                "INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, user_messages_count_all_time, is_left, "
                "last_message_at) VALUES (?, ?, ?, FALSE, NOW())", (uid, chat, n))
            await db.execute("INSERT INTO daily_user_stats (user_id, chat_id, date, message_count) VALUES (?, ?, ?, ?)",
                             (uid, chat, today, n))
        await db.execute("INSERT INTO user_warnings (chat_id, user_id, admin_id, reason) VALUES (-100, ?, ?, 'флуд')",
                         (P1, SENIOR))


class Client:
    """Запросы к ASGI-приложению в том же цикле событий, что и пул БД."""
    def __init__(self, app):
        import httpx
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    def __getattr__(self, method):
        return getattr(self.http, method)


async def checks():
    from FastAPI.auth import create_session_token
    import FastAPI.main as main
    from FastAPI.routers.bot_admin import people
    from infrastructure.database import get_pool
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import skins_v3 as skins_v3_repo
    from bot.chat import registry
    from bot.chat.framework import dispatch
    from bot.chat.moderation import is_blacklisted

    bot = FakeBot()
    people.set_bot(bot)
    client = Client(main.app)
    h = {uid: {"x-session-token": create_session_token(uid)} for uid in (DEV, HELPER, SENIOR, CODER, P1)}

    async def act(who, uid, **body):
        return await client.post(f"/bot-admin/api/player/{uid}/action", headers=h[who], json=body)

    async def chat_act(who, cid, **body):
        return await client.post(f"/bot-admin/api/chat/{cid}/action", headers=h[who], json=body)

    # Поиск
    assert (await client.get("/bot-admin/api/search?q=u2002", headers=h[P1])).status_code == 403
    found = (await client.get("/bot-admin/api/search?q=", headers=h[HELPER])).json()
    assert found["players"] and found["chats"][0]["id"] in (-100, -200), found
    found = (await client.get("/bot-admin/api/search?q=@u2002", headers=h[HELPER])).json()
    assert [p["id"] for p in found["players"]] == [P1] and found["players"][0]["messages"] == 125, found
    found = (await client.get("/bot-admin/api/search?q=2003", headers=h[HELPER])).json()
    assert [p["id"] for p in found["players"]] == [P2], found
    found = (await client.get("/bot-admin/api/search?q=основ", headers=h[HELPER])).json()
    assert [c["id"] for c in found["chats"]] == [-100] and found["chats"][0]["members"] == 3, found
    found = (await client.get("/bot-admin/api/search?q=-200", headers=h[HELPER])).json()
    assert [c["id"] for c in found["chats"]] == [-200], found
    found = (await client.get("/bot-admin/api/search?q=100%25", headers=h[HELPER])).json()   # % не шаблон
    assert found["chats"] == [] and found["players"] == [], found

    # Карточка игрока глазами хелпера
    card = (await client.get(f"/bot-admin/api/player/{P1}", headers=h[HELPER])).json()
    assert card["username"] == "u2002" and card["messages"]["total"] == 125, card
    assert [a["key"] for a in card["actions"]["member"]] == ["mute", "unmute", "unwarn_all"], card["actions"]
    assert card["actions"]["player"] == [], card["actions"]
    main_chat = next(c for c in card["chats"] if c["id"] == -100)
    assert main_chat["warns"] == 1 and not main_chat["muted"], main_chat
    assert (await client.get("/bot-admin/api/player/777", headers=h[HELPER])).status_code == 404

    # Модерация в чате
    r = await act(HELPER, P1, action="mute", chat_id=-100, minutes=60, reason="спам")
    assert r.status_code == 200, r.text
    assert ("restrict", -100, P1) in bot.calls
    assert (await act(HELPER, P1, action="ban", chat_id=-100)).status_code == 403          # бан — со ст. хелпера
    assert (await act(HELPER, CODER, action="mute", chat_id=-100, minutes=5)).status_code == 403   # роль выше
    assert (await act(CODER, DEV, action="mute", chat_id=-100, minutes=5)).status_code == 403      # разработчик
    assert (await act(HELPER, HELPER, action="mute", chat_id=-100, minutes=5)).status_code == 403  # сам себя
    r = await act(SENIOR, P1, action="ban", chat_id=-200, reason="x")
    assert r.status_code == 409 and "прав администратора" in r.json()["detail"], r.text
    r = await act(HELPER, P1, action="unwarn_all", chat_id=-100)
    assert r.json()["message"] == "Снято варнов: 1.", r.text
    card = (await client.get(f"/bot-admin/api/player/{P1}", headers=h[HELPER])).json()
    main_chat = next(c for c in card["chats"] if c["id"] == -100)
    assert main_chat["muted"] and main_chat["warns"] == 0, main_chat
    assert {"Мут", "Сняты все варны"} <= {x["title"] for x in card["history"]}, card["history"]
    assert (await act(HELPER, P1, action="unmute", chat_id=-100)).status_code == 200

    # Баланс, VIP, роль
    assert (await act(SENIOR, P1, action="balance", currency="mora", amount=500, reason="x")).status_code == 403
    r = await act(CODER, P1, action="balance", currency="mora", amount=500, reason="компенсация", request_id="r1")
    assert r.status_code == 200, r.text
    r = await act(CODER, P1, action="balance", currency="mora", amount=500, reason="компенсация", request_id="r1")
    assert r.status_code == 200   # повтор того же запроса не начисляет второй раз
    assert "не хватает" in (await act(CODER, P1, action="balance", currency="mora", amount=-1000, reason="x")).json()["detail"]
    assert "причину" in (await act(CODER, P1, action="balance", currency="mora", amount=5)).json()["detail"]
    assert "2 знаков" in (await act(CODER, P1, action="balance", currency="diamonds", amount="1.255", reason="x")).json()["detail"]
    assert (await act(CODER, P1, action="balance", currency="zarniki", amount=5, reason="x")).status_code == 400
    assert (await act(CODER, P1, action="balance", currency="essence", amount=30, reason="приз")).status_code == 200
    assert (await act(CODER, P1, action="balance", currency="essence", amount=-10, reason="ошибка")).status_code == 200
    assert (await act(CODER, P1, action="vip", days=7, reason="конкурс")).status_code == 200
    assert (await act(CODER, CODER, action="vip", days=7)).status_code == 403             # себе — нельзя
    card = (await client.get(f"/bot-admin/api/player/{P1}", headers=h[CODER])).json()
    assert card["balances"]["mora"] == 500 and card["balances"]["essence"] == 20, card["balances"]
    assert card["vip"] and card["vip"]["days_left"] == 7, card["vip"]
    assert [x["rank"] for x in card["ranks"]] == [0, 1, 2, 3, 4], card["ranks"]
    mora = [x for x in card["history"] if x["action"] == "balance" and "Мора" in x["text"]]
    assert [(x["text"], x["reason"]) for x in mora] == [("🪙 Мора +500", "компенсация")], mora   # без дубля
    assert (await act(CODER, P2, action="rank", rank=4)).status_code == 200
    assert (await act(CODER, P2, action="rank", rank=5)).status_code == 403
    assert (await act(CODER, P2, action="rank", rank=2)).status_code == 200
    assert (await act(DEV, P2, action="rank", rank=5)).status_code == 200
    assert (await act(CODER, P2, action="rank", rank=0)).status_code == 403              # теперь равен по роли
    assert (await act(DEV, P2, action="rank", rank=6)).status_code == 400

    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        assert await skins_v3_repo.essence_balance(db, P1) == 20

        async def say(text, uid):
            m = FakeMessage(text, uid)
            await dispatch(registry, m, bot, db)
            return " | ".join(m.replies)

        # Бот не отвечает игроку
        assert await say("бот я", P1)
        assert (await act(SENIOR, P1, action="block", reason="абуз")).status_code == 200
        assert await say("бот я", P1) == ""
        card = (await client.get(f"/bot-admin/api/player/{P1}", headers=h[HELPER])).json()
        assert card["blocked"]["reason"] == "абуз", card["blocked"]
        assert (await act(SENIOR, P1, action="unblock")).status_code == 200
        assert await say("бот я", P1)

        # Бан во всех чатах
        bot.calls.clear()
        assert (await act(SENIOR, P1, action="global_ban")).status_code == 403
        r = await act(CODER, P1, action="global_ban", reason="мошенник")
        assert r.json()["message"] == "Забанен в чатах: 2, не вышло: 1.", r.text
        assert await is_blacklisted(db, -300, P1)
        card = (await client.get(f"/bot-admin/api/player/{P1}", headers=h[HELPER])).json()
        assert card["global_ban"]["reason"] == "мошенник" and all(c["left"] for c in card["chats"]), card
        r = await act(CODER, P1, action="global_unban")
        assert r.status_code == 200 and not await is_blacklisted(db, -300, P1), r.text
        assert ("unban", -100, P1) in bot.calls

    # Карточка чата и действия с ним
    card = (await client.get("/bot-admin/api/chat/-100", headers=h[HELPER])).json()
    assert card["title"] == "Основной чат" and card["messages"]["today"]["messages"] == 167, card["messages"]
    assert [x["id"] for x in card["top"]] == [P2, CODER], card["top"]   # P1 вышел после глобального бана
    assert [a["key"] for a in card["actions"]["chat"]] == ["close", "open"], card["actions"]
    assert (await chat_act(HELPER, -100, action="close")).status_code == 200
    assert (await chat_act(HELPER, -100, action="warn_limit", value=5)).status_code == 403
    assert (await chat_act(SENIOR, -100, action="warn_limit", value=5)).status_code == 200
    assert (await chat_act(SENIOR, -100, action="warn_limit", value=50)).status_code == 400
    assert (await chat_act(CODER, -100, action="message", text="Привет!")).status_code == 200
    assert ("send", -100, "Привет!") in bot.calls
    assert (await chat_act(CODER, -100, action="leave")).status_code == 403
    assert (await client.post("/bot-admin/api/switches", headers=h[DEV],
                              json={"feature": "group:warps", "chat_id": -100, "enabled": False})).status_code == 200
    card = (await client.get("/bot-admin/api/chat/-100", headers=h[HELPER])).json()
    assert card["closed"] and card["warn_limit"] == 5, card
    assert card["switched_off"] and card["switched_off"][0]["key"] == "group:warps", card["switched_off"]
    assert {"Чат закрыт", "Лимит варнов", "Сообщение от бота"} <= {x["title"] for x in card["history"]}
    assert (await chat_act(DEV, -100, action="leave")).status_code == 200
    assert (await client.get("/bot-admin/api/chat/-999", headers=h[HELPER])).status_code == 404


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(prepare())
    loop.run_until_complete(checks())
    print("OK: bot admin players, chats and global moderation on PostgreSQL")


main()
