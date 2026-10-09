"""Жалобы («бот жалоба» -> очередь в админке), «бот под защитой» и рассылка из админки.

Запуск: python tools/test_bot_admin_reports_pg.py --dsn postgresql://... (пустая тестовая БД!)
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

DEV, HELPER, CODER, P1, P2, P3 = 1001, 3003, 5005, 2002, 2003, 2004


class FakeBot:
    def __init__(self):
        self.sent = []

    async def me(self):
        return SimpleNamespace(id=999, username="predvestnik_bot")

    async def get_chat_administrators(self, chat_id):
        return [SimpleNamespace(status="creator", user=SimpleNamespace(id=P1))]

    async def send_message(self, chat_id, text, **kw):
        if chat_id in (P3, -200):   # P3 не открывал личку, из -200 бота выгнали
            raise RuntimeError("Forbidden: bot can't initiate conversation")
        self.sent.append((chat_id, text))


class FakeMessage:
    def __init__(self, text, uid, chat=-100, reply_to=None):
        self.text, self.caption, self.entities = text, None, []
        self.from_user = SimpleNamespace(id=uid, is_bot=False, username=f"u{uid}", full_name=f"U{uid}",
                                         first_name=f"U{uid}")
        self.chat = SimpleNamespace(id=chat, type="supergroup", title="Тест")
        self.reply_to_message = reply_to
        self.message_id = 1
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
    from bot.startup_schema import ensure_runtime_schema
    from FastAPI.auth import create_session_token
    from FastAPI.routers.bot_admin import people
    from services import broadcasts, global_moderation
    import FastAPI.main as main

    await create_pool()
    await init_db()
    await ensure_runtime_schema(get_pool())
    await ensure_chat_schema()
    await ensure_chat_schema()
    bot = FakeBot()
    people.set_bot(bot)
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        for uid, rank in ((DEV, 0), (HELPER, 3), (CODER, 5), (P1, 0), (P2, 0), (P3, 0)):
            await db.execute("INSERT INTO users (user_tg_id, user_tg_username, bot_rank) VALUES (?, ?, ?)",
                             (uid, f"u{uid}", rank))
        for chat in (-100, -200):
            await db.execute("INSERT INTO chat_settings (chat_id, chat_title) VALUES (?, 'Чат')", (chat,))
        for uid in (P1, P2, P3):
            await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id) VALUES (?, -100)", (uid,))
        await db.execute("INSERT INTO chat_links (main_chat_id, admin_chat_id) VALUES (-100, -555)")

        async def say(text, uid, **kw):
            m = FakeMessage(text, uid, **kw)
            await dispatch(registry, m, bot, db)
            return " | ".join(m.replies)

        # «бот под защитой»
        assert "никто" in await say("бот под защитой", P2)
        assert "защищён" in await say("бот защита, @u2003 2д", DEV)
        assert "иммунитет" in await say("бот иммунитет, @u2004", DEV)
        out = await say("бот кто под защитой", P2)
        assert "Иммунитет" in out and "u2004" in out and "Защита" in out and "u2003 · до " in out, out
        assert out.index("u2004") < out.index("u2003"), out

        # «бот жалоба» ответом на сообщение нарушителя
        bad = SimpleNamespace(from_user=SimpleNamespace(id=P3, is_bot=False, username="u2004", full_name="U2004",
                                                        first_name="U2004"),
                              text="ты дурак", caption=None, message_id=77)
        assert "причину" in await say("бот жалоба", P2, reply_to=bad)
        out = await say("бот жалоба оскорбления", P2, reply_to=bad)
        assert "принята" in out, out
        assert bot.sent[-1][0] == -555 and "Жалоба №" in bot.sent[-1][1] and "ты дурак" in bot.sent[-1][1], bot.sent
        assert "уже в очереди" in await say("бот репорт ещё раз", P2, reply_to=bad)
        assert "нельзя" in await say("бот report, @u2003 сам себя", P2)
        out = await say("бот пожаловаться, @u2003 спам", P1)
        assert "принята" in out, out

    client = Client(main.app)
    h = {uid: {"x-session-token": create_session_token(uid)} for uid in (DEV, HELPER, CODER, P1)}
    assert (await client.get("/bot-admin/api/reports", headers=h[P1])).status_code == 403
    me = (await client.get("/bot-admin/api/me", headers=h[HELPER])).json()
    assert [s["key"] for s in me["sections"]] == ["people", "reports"], me
    data = (await client.get("/bot-admin/api/reports", headers=h[HELPER])).json()
    assert data["counts"]["new"] == 2 and len(data["items"]) == 2, data
    first = data["items"][0]
    assert first["target"]["id"] == P3 and first["message_text"] == "ты дурак" and first["reason"] == "оскорбления", first
    rid = first["id"]
    post = lambda rid, **b: client.post(f"/bot-admin/api/reports/{rid}", headers=h[HELPER], json=b)
    assert (await post(rid, action="take")).status_code == 200
    assert (await post(rid, action="nope")).status_code == 400
    assert (await post(rid, action="resolve", note="выдан мут")).status_code == 200
    assert (await post(rid, action="reject")).status_code == 409                 # уже закрыта
    assert bot.sent[-1] == (P2, f"✅ Ваша жалоба №{rid} рассмотрена: нарушение подтверждено. Спасибо!"), bot.sent
    assert (await post(data["items"][1]["id"], action="reject")).status_code == 200
    data = (await client.get("/bot-admin/api/reports?kind=closed", headers=h[HELPER])).json()
    assert [x["status"] for x in data["items"]] == ["rejected", "resolved"], data["items"]
    assert data["items"][1]["note"] == "выдан мут" and data["items"][1]["handled_by"]["id"] == HELPER, data["items"][1]
    assert (await client.get("/bot-admin/api/reports", headers=h[HELPER])).json()["items"] == []
    card = (await client.get(f"/bot-admin/api/player/{P3}", headers=h[HELPER])).json()
    assert "Жалоба: нарушение подтверждено" in {x["title"] for x in card["history"]}, card["history"]

    # Рассылка
    broadcasts.PAUSE = {"chats": 0, "players": 0}
    assert (await client.get("/bot-admin/api/broadcasts", headers=h[HELPER])).status_code == 403
    async with get_pool().acquire() as conn:
        await global_moderation.block(PGAdapter(conn), P1, DEV, "тест")
    info = (await client.get("/bot-admin/api/broadcasts", headers=h[CODER])).json()
    assert info["sizes"] == {"chats": 2, "players": 5}, info          # P1 заблокирован — без него
    bad_req = await client.post("/bot-admin/api/broadcasts", headers=h[CODER], json={"audience": "players", "text": " "})
    assert bad_req.status_code == 400
    bot.sent.clear()
    r = await client.post("/bot-admin/api/broadcasts", headers=h[CODER],
                          json={"audience": "players", "text": "Обновление!", "request_id": "r1"})
    assert r.status_code == 200 and "5 получателей" in r.json()["message"], r.text
    again = await client.post("/bot-admin/api/broadcasts", headers=h[CODER],
                              json={"audience": "players", "text": "Обновление!", "request_id": "r1"})
    assert again.json()["id"] == r.json()["id"] and again.json()["message"] == "Уже запущена."
    await asyncio.gather(*list(broadcasts._tasks.values()))
    assert sorted(c for c, t in bot.sent) == sorted([DEV, HELPER, CODER, P2]), bot.sent
    item = (await client.get("/bot-admin/api/broadcasts", headers=h[CODER])).json()["items"][0]
    assert (item["status"], item["total"], item["sent"], item["failed"]) == ("done", 5, 4, 1), item
    r = await client.post("/bot-admin/api/broadcasts", headers=h[CODER],
                          json={"audience": "chats", "text": "Всем чатам", "request_id": "r2"})
    assert r.status_code == 200
    await asyncio.gather(*list(broadcasts._tasks.values()))
    item = (await client.get("/bot-admin/api/broadcasts", headers=h[CODER])).json()["items"][0]
    assert (item["status"], item["sent"], item["failed"]) == ("done", 1, 1), item
    assert (await client.post(f"/bot-admin/api/broadcasts/{item['id']}/stop", headers=h[CODER])).status_code == 409

    # 18+ варпы: настройка на сайте и команда в чате — один и тот же флаг.
    hp = {"x-session-token": create_session_token(P2)}
    assert (await client.get("/profile/warp-prefs", headers=hp)).json() == {"adult": False}
    r = await client.post("/profile/warp-prefs", headers=hp, json={"enabled": True})
    assert r.status_code == 200 and r.json() == {"adult": True}, r.text
    async with get_pool().acquire() as conn:
        m = FakeMessage("бот 18+", P2)
        await dispatch(registry, m, bot, PGAdapter(conn))
        assert "сейчас включены" in m.replies[0], m.replies
        m = FakeMessage("бот 18+ выкл", P2)
        await dispatch(registry, m, bot, PGAdapter(conn))
    assert (await client.get("/profile/warp-prefs", headers=hp)).json() == {"adult": False}


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run())
    print("OK: reports, protected list and broadcasts on PostgreSQL")


main()
