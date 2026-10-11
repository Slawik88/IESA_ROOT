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
        self.markups = []
        self.sent = []

    async def me(self):
        return SimpleNamespace(id=999, username="predvestnik_bot")

    async def get_chat_administrators(self, chat_id):
        return [SimpleNamespace(status="creator", user=SimpleNamespace(id=P1))]

    async def send_message(self, chat_id, text, **kw):
        if chat_id in (P3, -200):   # P3 не открывал личку, из -200 бота выгнали
            raise RuntimeError("Forbidden: bot can't initiate conversation")
        if kw.get("parse_mode") == "HTML" and text.count("<b>") != text.count("</b>"):
            raise RuntimeError("Telegram server says - Bad Request: can't parse entities: can't find end tag")
        self.sent.append((chat_id, text, kw.get("parse_mode")) if kw.get("parse_mode") else (chat_id, text))
        if kw.get("reply_markup") is not None:
            self.markups.append((chat_id, kw["reply_markup"].inline_keyboard[0][0].text, kw["reply_markup"].inline_keyboard[0][0].url))


class FakeMessage:
    def __init__(self, text, uid, chat=-100, reply_to=None, chat_type="supergroup"):
        self.text, self.caption, self.entities = text, None, []
        self.from_user = SimpleNamespace(id=uid, is_bot=False, username=f"u{uid}", full_name=f"U{uid}",
                                         first_name=f"U{uid}")
        self.chat = SimpleNamespace(id=chat, type=chat_type, title="Тест")
        self.reply_to_message = reply_to
        self.message_id = 1
        self.message_thread_id = None
        self.replies = []
        self.deleted = False
        self.can_delete = True

    async def reply(self, text, **kw):
        self.replies.append(text)
        self.kw = kw

    async def answer(self, text, **kw):
        self.replies.append(text)

    async def delete(self):
        if not self.can_delete:
            raise RuntimeError("Bad Request: message can't be deleted")
        self.deleted = True


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
        await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, chat_rank) VALUES (?, -100, 5)", (CODER,))
        await db.execute("INSERT INTO chat_links (main_chat_id, admin_chat_id) VALUES (-100, -555)")

        async def say(text, uid, **kw):
            m = FakeMessage(text, uid, **kw)
            await dispatch(registry, m, bot, db)
            say.last = m
            return " | ".join(m.replies)

        # «бот под защитой»
        assert "никто" in await say("бот под защитой", P2)
        assert "защищён" in await say("бот защита, @u2003 2д", DEV)
        assert "иммунитет" in await say("бот иммунитет, @u2004", DEV)
        out = await say("бот кто под защитой", P2)
        assert "Иммунитет" in out and "u2004" in out and "Защита" in out and "u2003 · до " in out, out
        assert out.index("u2004") < out.index("u2003"), out
        # Короткие алиасы: «рест» = «защита», «кто защита» и «кто рест» = «под защитой» (не путаются с профилем «бот кто»)
        for alias in ("бот кто защита", "бот кто рест", "бот Кто  Рест"):
            assert await say(alias, P2) == out, alias
        assert "защищён" in await say("бот рест, @u2002 3д", DEV)
        assert "u2002 · до " in await say("бот кто рест", P2)
        assert "Кто это" not in out and "Профиль" not in out

        # «бот жалоба» ответом на сообщение нарушителя
        bad = SimpleNamespace(from_user=SimpleNamespace(id=P3, is_bot=False, username="u2004", full_name="U2004",
                                                        first_name="U2004"),
                              text="ты дурак", caption=None, message_id=77)
        assert "причину" in await say("бот жалоба", P2, reply_to=bad)
        assert not say.last.deleted                                          # ошибка формата: команду не трогаем
        bot.sent.clear()
        out = await say("бот жалоба оскорбления", P2, reply_to=bad)
        # Анонимно: команда убрана из чата, в чат ничего не ответили, автору ушло в личку.
        assert say.last.deleted and out == "", (say.last.deleted, out)
        assert bot.sent[0][0] == P2 and "принята" in bot.sent[0][1] and "анонимна" in bot.sent[0][1], bot.sent
        admin_msg = next(x for x in bot.sent if x[0] == -555)
        assert "Жалоба №" in admin_msg[1] and "ты дурак" in admin_msg[1] and "оскорбления" in admin_msg[1], admin_msg
        assert "U2002" not in admin_msg[1] and "u2002" not in admin_msg[1] and "от " not in admin_msg[1].split("\n")[0], admin_msg
        assert "Не удалось" not in admin_msg[1] and "не удалось" not in admin_msg[1]
        # По умолчанию отчёт идёт ещё и модераторам чата (ранг от 4): CODER. Автору — только своё подтверждение.
        dms = [x[0] for x in bot.sent if x[0] != -555][1:]
        assert CODER in dms and P2 not in dms and HELPER not in dms and P3 not in dms, bot.sent
        from bot.chat.reports import _message_link
        assert _message_link(-1001234567890, 5) == "https://t.me/c/1234567890/5" and _message_link(-100, 5) == "" \
            and _message_link(555, 5) == ""
        assert all("t.me/c" not in x[1] for x in bot.sent), bot.sent
        bot.sent.clear()
        await say("бот репорт ещё раз", P2, reply_to=bad)
        assert bot.sent == [(P2, "📨 Ваша жалоба на этого игрока уже в очереди.", "HTML")], bot.sent
        await say("бот report, @u2003 сам себя", P2)
        assert "нельзя" in bot.sent[-1][1] and say.last.deleted, bot.sent
        out = await say("бот пожаловаться, @u2003 спам", P1)
        assert say.last.deleted and out == "", out
        # Личка автора закрыта: короткое «принята» в чат без имён.
        bot.sent.clear()
        await say("бот пожаловаться, @u2003 спам", P3)
        assert say.last.deleted and bot.sent[0] == (-100, "📨 Жалоба принята.", "HTML"), bot.sent
        # Команду убрать нельзя (нет права): отвечаем в чат и говорим админам, как это исправить.
        bot.sent.clear()
        m = FakeMessage("бот жалоба, @u2004 грубит", P1)
        m.can_delete = False
        await dispatch(registry, m, bot, db)
        assert not m.deleted and "принята" in m.replies[0], (m.deleted, m.replies)
        assert any(x[0] == -555 and "право удалять" in x[1] for x in bot.sent), bot.sent
        await db.execute("DELETE FROM bot_reports WHERE reporter_id = ? OR reason = 'грубит'", (P3,))   # лишние для проверок ниже


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

    # Анонимность в админке: автора видят только с роли из настроек жалоб (по умолчанию 5), остальным «скрыт».
    r = (await client.get("/bot-admin/api/reports?kind=closed", headers=h[HELPER])).json()
    assert r["can_see_reporter"] is False and all(x["reporter"] is None and x["reporter_hidden"] for x in r["items"]), r
    r = (await client.get("/bot-admin/api/reports?kind=closed", headers=h[CODER])).json()
    assert r["can_see_reporter"] is True and {x["reporter"]["id"] for x in r["items"]} == {P1, P2}, r
    # Отдельные настройки жалоб: только владелец бота/разработчик (раздел «Настройки»).
    assert (await client.get("/bot-admin/api/settings", headers=h[HELPER])).status_code == 403
    st = (await client.get("/bot-admin/api/settings", headers=h[CODER])).json()
    assert st["reports"] == {"to_admin_chat": True, "dm_chat_rank": 4, "dm_staff_rank": 0, "reporter_min_rank": 5}, st["reports"]
    assert st["report_options"]["chat_ranks"][0]["value"] == 1 and st["report_options"]["staff_ranks"][-1]["value"] == 6
    bad_conf = await client.post("/bot-admin/api/settings/reports", headers=h[CODER], json={"dm_chat_rank": 99})
    assert bad_conf.status_code == 400, bad_conf.text
    conf = await client.post("/bot-admin/api/settings/reports", headers=h[CODER],
                             json={"to_admin_chat": False, "dm_chat_rank": 0, "dm_staff_rank": 3, "reporter_min_rank": 3})
    assert conf.status_code == 200 and conf.json()["reports"] == {
        "to_admin_chat": False, "dm_chat_rank": 0, "dm_staff_rank": 3, "reporter_min_rank": 3}, conf.text
    r = (await client.get("/bot-admin/api/reports?kind=closed", headers=h[HELPER])).json()
    assert r["can_see_reporter"] is True and all(x["reporter"] for x in r["items"]), r         # теперь и хелпер видит
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        bot.sent.clear()
        m = FakeMessage("бот жалоба, @u2004 флуд", P1)
        await dispatch(registry, m, bot, db)
        dms = [x[0] for x in bot.sent][1:]
        assert -555 not in dms and CODER in dms and HELPER in dms and DEV in dms and P1 not in dms, bot.sent   # персонал, а не админ-чат
        await db.execute("DELETE FROM bot_reports WHERE reason = 'флуд'")
    feed = (await client.get("/bot-admin/api/journal?days=1", headers=h[DEV])).json()
    assert "Настройки жалоб" in {x["title"] for x in feed["items"]}, [x["title"] for x in feed["items"]]
    await client.post("/bot-admin/api/settings/reports", headers=h[CODER],
                      json={"to_admin_chat": True, "dm_chat_rank": 4, "dm_staff_rank": 0, "reporter_min_rank": 5})

    # «бот админка»: в личке кнопка web_app, в группе прямая ссылка на мини-приложение (внутри Telegram, не во внешнем браузере)
    os.environ["MINIAPP_URL"], os.environ["MINIAPP_SHORT_NAME"] = "https://app.example/?x=1", "pv"
    async with get_pool().acquire() as conn:
        async def panel(uid, **kw):
            m = FakeMessage("бот админка", uid, **kw)
            await dispatch(registry, m, bot, PGAdapter(conn))
            return m
        assert "только персоналу" in (await panel(P2)).replies[-1]
        btn = (await panel(DEV)).kw["reply_markup"].inline_keyboard[0][0]
        assert btn.url == "https://t.me/predvestnik_bot/pv?startapp=admin" and btn.web_app is None, btn
        btn = (await panel(DEV, chat=DEV, chat_type="private")).kw["reply_markup"].inline_keyboard[0][0]
        assert btn.web_app.url == "https://app.example/bot-admin" and btn.url is None, btn
        os.environ["MINIAPP_SHORT_NAME"] = ""
        assert (await panel(DEV)).kw["reply_markup"].inline_keyboard[0][0].url == "https://app.example/bot-admin"

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
    assert again.json()["id"] == r.json()["id"] and again.json()["message"] == "Уже создана."
    await asyncio.gather(*list(broadcasts._tasks.values()))
    assert sorted(x[0] for x in bot.sent) == sorted([DEV, HELPER, CODER, P2]), bot.sent
    item = (await client.get("/bot-admin/api/broadcasts", headers=h[CODER])).json()["items"][0]
    assert (item["status"], item["total"], item["sent"], item["failed"]) == ("done", 5, 4, 1), item
    r = await client.post("/bot-admin/api/broadcasts", headers=h[CODER],
                          json={"audience": "chats", "text": "Всем чатам", "request_id": "r2"})
    assert r.status_code == 200
    await asyncio.gather(*list(broadcasts._tasks.values()))
    item = (await client.get("/bot-admin/api/broadcasts", headers=h[CODER])).json()["items"][0]
    assert (item["status"], item["sent"], item["failed"]) == ("done", 1, 1), item
    assert (await client.post(f"/bot-admin/api/broadcasts/{item['id']}/stop", headers=h[CODER])).status_code == 409
    # HTML: пробная отправка себе и проверка разметки до рассылки
    bot.sent.clear()
    r = await client.post("/bot-admin/api/broadcasts/test", headers=h[CODER], json={"text": "<b>Привет</b>", "html": True})
    assert r.status_code == 200 and bot.sent == [(CODER, "<b>Привет</b>", "HTML")], (r.text, bot.sent)
    r = await client.post("/bot-admin/api/broadcasts/test", headers=h[CODER], json={"text": "<b>Привет", "html": True})
    assert r.status_code == 400 and "HTML" in r.json()["detail"], r.text
    r = await client.post("/bot-admin/api/broadcasts", headers=h[CODER],
                          json={"audience": "chats", "text": "<b>сломано", "html": True, "request_id": "r3"})
    assert r.status_code == 400, r.text                               # битый HTML не уходит в чаты
    r = await client.post("/bot-admin/api/broadcasts", headers=h[CODER],
                          json={"audience": "chats", "text": "<b>Всем</b>", "html": True, "request_id": "r4"})
    assert r.status_code == 200, r.text
    await asyncio.gather(*list(broadcasts._tasks.values()))
    assert (-100, "<b>Всем</b>", "HTML") in bot.sent, bot.sent
    assert (await client.get("/bot-admin/api/broadcasts", headers=h[CODER])).json()["items"][0]["html"] is True


    # Рассылка по сегментам: счётчик получателей, кнопка, шаблоны, отчёт, повтор, расписание, продолжение.
    api = "/bot-admin/api/broadcasts"
    async def post(path, **body):
        return await client.post(api + path, headers=h[CODER], json=body)
    async def idle():
        if broadcasts._tasks:
            await asyncio.gather(*list(broadcasts._tasks.values()))
    async def count(segment):
        r = await post("/preview", segment=segment)
        assert r.status_code == 200, r.text
        return r.json()["count"]
    # Чат, из которого бота удалили, и игрок, заблокировавший бота, в рассылку не попадают
    async with get_pool().acquire() as conn:
        d0 = PGAdapter(conn)
        await d0.execute("UPDATE chat_settings SET bot_left_at = NOW() WHERE chat_id = -200")
        await d0.execute("UPDATE users SET dm_blocked_at = NOW() WHERE user_tg_id = ?", (P3,))
    assert await count({"kind": "chats"}) == 1 and await count({"kind": "players"}) == 4
    async with get_pool().acquire() as conn:
        d0 = PGAdapter(conn)
        await d0.execute("UPDATE chat_settings SET bot_left_at = NULL WHERE chat_id = -200")
        await d0.execute("UPDATE users SET dm_blocked_at = NULL WHERE user_tg_id = ?", (P3,))
    async with get_pool().acquire() as conn:
        d = PGAdapter(conn)
        await d.execute("INSERT INTO daily_user_stats (user_id, chat_id, date) VALUES (?, -100, ?)",
                        (P2, __import__("bot.chat.tracking", fromlist=["local_now"]).local_now().date().isoformat()))
        await d.execute("INSERT INTO vip_subscriptions (user_id, tier, expires_at) VALUES (?, 'vip', NOW() + INTERVAL '5 days')", (P2,))
        await d.execute("UPDATE user_chat_stats SET user_messages_count_all_time = 40 WHERE user_tg_id = ? AND chat_tg_id = -100", (P2,))
    assert await count({"kind": "players"}) == 5
    assert await count({"kind": "chats"}) == 2
    assert await count({"kind": "chats", "chats": [-100]}) == 1
    assert await count({"kind": "chats", "active_days": 7}) == 1                    # писали в -100, в -200 никто
    assert await count({"kind": "players", "vip": True}) == 1
    assert await count({"kind": "players", "vip": False}) == 4
    assert await count({"kind": "players", "players": [P2, P3]}) == 2
    assert await count({"kind": "players", "chats": [-100]}) == 3                   # P1 заблокирован
    assert await count({"kind": "players", "active_days": 7}) == 3                  # P2, P3, CODER: сообщения только что (P1 заблокирован)
    assert await count({"kind": "players", "new_days": 7}) == 3
    assert await count({"kind": "players", "min_messages": 30}) == 1
    assert await count({"kind": "players", "vip": True, "min_messages": 100}) == 0
    for bad in ({"kind": "nobody"}, {"kind": "players", "active_days": 9999}, {"kind": "players", "players": "x"},
                {"kind": "chats", "chats": ["abc"]}):
        assert (await post("/preview", segment=bad)).status_code == 400, bad
    # Кнопка: проверки
    for button in ({"text": "Открыть"}, {"url": "https://x.y"}, {"text": "Да", "url": "http://x.y"},
                   {"text": "Да", "url": "https://x y"}, {"text": "я" * 65, "url": "https://x.y"}):
        assert (await post("/test", text="Привет", button=button)).status_code == 400, button
    bot.sent.clear(); bot.markups.clear()
    r = await post("/test", text="Привет", button={"text": "Играть", "url": "https://t.me/predvestnik_bot"})
    assert r.status_code == 200 and bot.markups == [(CODER, "Играть", "https://t.me/predvestnik_bot")], (r.text, bot.markups)

    # Шаблоны
    assert (await post("/templates", title="", text="x")).status_code == 400
    r = await post("/templates", title="Новости", text="<b>Привет</b>", html=True,
                   button={"text": "Играть", "url": "https://t.me/predvestnik_bot"})
    assert r.status_code == 200 and r.json()["items"][0]["title"] == "Новости" and r.json()["items"][0]["html"], r.text
    tid = r.json()["id"]
    assert (await client.get(api, headers=h[CODER])).json()["templates"][0]["button"]["text"] == "Играть"
    assert (await client.delete(f"{api}/templates/{tid}", headers=h[CODER])).json()["items"] == []
    assert (await client.delete(f"{api}/templates/{tid}", headers=h[CODER])).status_code == 404

    # Выбранные игроки + кнопка: P2 получит, P3 не открывал диалог — отчёт покажет причину
    bot.sent.clear(); bot.markups.clear()
    r = await post("", audience="players", text="Только вам", request_id="s1", segment={"kind": "players", "players": [P2, P3]},
                   button={"text": "Играть", "url": "https://t.me/predvestnik_bot"})
    assert r.status_code == 200 and "2 получателей" in r.json()["message"], r.text
    first = r.json()["id"]
    await idle()
    btn = "https://t.me/predvestnik_bot"
    assert [x[0] for x in bot.sent] == [CODER, P2], bot.sent                       # сначала проверка кнопки на себе
    assert bot.markups == [(CODER, "Играть", btn), (P2, "Играть", btn)], bot.markups
    rep = (await client.get(f"{api}/{first}", headers=h[CODER])).json()
    assert (rep["sent"], rep["failed"], rep["pending"]) == (1, 1, 0), rep
    assert rep["reasons"] == [{"code": "no_dialog", "title": "Не открывали диалог с ботом", "count": 1}], rep["reasons"]
    assert rep["failed_sample"][0]["id"] == P3 and rep["broadcast"]["audience_title"].startswith("В личку: выбранные игроки (2)")
    assert (await client.get(f"{api}/999999", headers=h[CODER])).status_code == 404
    # Повтор недоставленным: новая рассылка только для P3 (он опять не получит — доставка отмечена как failed)
    bot.sent.clear()
    r = await client.post(f"{api}/{first}/retry", headers=h[CODER])
    assert r.status_code == 200 and "1 получателей" in r.json()["message"], r.text
    await idle()
    again = (await client.get(f"{api}/{r.json()['id']}", headers=h[CODER])).json()
    assert again["broadcast"]["segment"]["retry_of"] == first and again["failed"] == 1 and not bot.sent, again
    ok_one = (await client.get(api, headers=h[CODER])).json()["items"]
    assert (await client.post(f"{api}/{ok_one[0]['id']}/resume", headers=h[CODER])).status_code == 409   # всё уже обработано

    # Расписание: прошлое нельзя, будущее ждёт, отмена, наступившее запускается планировщиком
    assert (await post("", audience="chats", text="Позже", scheduled_at="2020-01-01T00:00:00Z")).status_code == 400
    assert (await post("", audience="chats", text="Позже", scheduled_at="не время")).status_code == 400
    future = (__import__("datetime").datetime.now(__import__("datetime").timezone.utc) + __import__("datetime").timedelta(hours=2)).isoformat()
    r = await post("", audience="chats", text="Позже", request_id="s2", scheduled_at=future, segment={"kind": "chats", "chats": [-100]})
    assert r.status_code == 200 and "запланирована" in r.json()["message"], r.text
    sched = r.json()["id"]
    top = (await client.get(api, headers=h[CODER])).json()["items"][0]
    assert top["id"] == sched and top["status"] == "scheduled" and top["total"] == 0, top
    assert await broadcasts.launch_due(bot, broadcasts.pool_db_factory()) is None                    # время не пришло
    assert (await client.post(f"{api}/{sched}/stop", headers=h[CODER])).status_code == 200            # отмена запланированной
    assert (await client.get(f"{api}/{sched}", headers=h[CODER])).json()["broadcast"]["status"] == "stopped"
    r = await post("", audience="chats", text="Скоро", request_id="s3", scheduled_at=future, segment={"kind": "chats", "chats": [-100]})
    sched = r.json()["id"]
    async with get_pool().acquire() as conn:
        await PGAdapter(conn).execute("UPDATE bot_broadcasts SET scheduled_at = NOW() - INTERVAL '1 minute' WHERE id = ?", (sched,))
    bot.sent.clear()
    assert await broadcasts.launch_due(bot, broadcasts.pool_db_factory()) == sched
    await idle()
    assert bot.sent == [(-100, "Скоро")], bot.sent
    done = (await client.get(f"{api}/{sched}", headers=h[CODER])).json()
    assert (done["broadcast"]["status"], done["sent"], done["broadcast"]["total"]) == ("done", 1, 1), done

    # Продолжить прерванную: получатели зафиксированы, дошедшим не отправляем второй раз
    made = None
    async with get_pool().acquire() as conn:
        made = await broadcasts.create(PGAdapter(conn), CODER, "players", "Дослать", "s4", False,
                                       segment={"kind": "players", "players": [DEV, HELPER, P2]})
        await PGAdapter(conn).execute("UPDATE bot_broadcast_targets SET status = 'sent' WHERE broadcast_id = ? AND target_id = ?",
                                      (made.id, DEV))
        await PGAdapter(conn).execute("UPDATE bot_broadcasts SET status = 'interrupted' WHERE id = ?", (made.id,))
    bot.sent.clear()
    r = await client.post(f"{api}/{made.id}/resume", headers=h[CODER])
    assert r.status_code == 200 and "осталось 2" in r.json()["message"], r.text
    await idle()
    assert sorted(x[0] for x in bot.sent) == sorted([HELPER, P2]), bot.sent
    # Одновременно идёт одна рассылка
    async with get_pool().acquire() as conn:
        busy = await broadcasts.create(PGAdapter(conn), CODER, "players", "Занято", "s5", False, segment={"kind": "players", "players": [DEV]})
    r = await post("", audience="players", text="Вторая", request_id="s6")
    assert r.status_code == 400 and "другая рассылка" in r.json()["detail"], r.text
    async with get_pool().acquire() as conn:
        await PGAdapter(conn).execute("UPDATE bot_broadcasts SET status = 'stopped' WHERE id = ?", (busy.id,))
    feed = (await client.get("/bot-admin/api/journal?days=1", headers=h[DEV])).json()
    titles = {x["title"] for x in feed["items"]}
    assert {"Рассылка", "Шаблон рассылки", "Рассылка продолжена", "Рассылка остановлена или отменена"} <= titles, titles

    # Если старт бота не создал таблицы, разделы создают их сами и не висят на загрузке.
    from FastAPI.routers.bot_admin import broadcasts as broadcasts_api, reports as reports_api
    async with get_pool().acquire() as conn:
        await PGAdapter(conn).execute("DROP TABLE bot_reports")
        await PGAdapter(conn).execute("DROP TABLE bot_broadcasts")
    reports_api._ready = broadcasts_api._ready = False
    r = await client.get("/bot-admin/api/reports", headers=h[HELPER])
    assert r.status_code == 200 and r.json()["items"] == [], r.text
    r = await client.get("/bot-admin/api/broadcasts", headers=h[CODER])
    assert r.status_code == 200 and r.json()["items"] == [], r.text

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
