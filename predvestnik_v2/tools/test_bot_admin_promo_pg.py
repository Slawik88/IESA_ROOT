"""Новая админка (/bot-admin) и промокоды: права, создание, активация в чате, лимиты.

Запуск: python tools/test_bot_admin_promo_pg.py --dsn postgresql://... (пустая тестовая БД!)
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


class FakeBot:
    async def me(self):
        return SimpleNamespace(id=999, username="predvestnik_bot")


async def prepare():
    from infrastructure.database import create_pool, get_pool
    from infrastructure.pg_adapter import PGAdapter
    from bot.core.database import init_db
    from bot.chat.schema import ensure_chat_schema
    from bot.startup_schema import ensure_runtime_schema
    await create_pool()
    await init_db()
    await ensure_runtime_schema(get_pool())
    await ensure_chat_schema()
    await ensure_chat_schema()   # повторный запуск безопасен
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        for uid in (1001, 2002, 2003, 2004, 2005, 3003):
            await db.execute("INSERT INTO users (user_tg_id, user_tg_username) VALUES (?, ?) ON CONFLICT DO NOTHING",
                             (uid, f"u{uid}"))
        await db.execute("UPDATE users SET bot_rank = 3 WHERE user_tg_id = 3003")   # хелпер: промокоды не видит
        await db.execute("UPDATE users SET bot_rank = 5 WHERE user_tg_id = 2005")   # разработчик: промокоды видит, Зарники класть не может
        for chat, title in ((-100, "Основной чат"), (-200, "Другой чат")):
            await db.execute("INSERT INTO chat_settings (chat_id, chat_title) VALUES (?, ?) ON CONFLICT DO NOTHING",
                             (chat, title))


class Client:
    """Запросы к ASGI-приложению в том же цикле событий, что и пул БД."""
    def __init__(self, app):
        import httpx
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    def __getattr__(self, method):
        return getattr(self.http, method)


async def http_checks():
    from FastAPI.auth import create_session_token
    import FastAPI.main as main
    client = Client(main.app)
    dev = {"x-session-token": create_session_token(1001)}
    helper = {"x-session-token": create_session_token(3003)}
    player = {"x-session-token": create_session_token(2002)}

    page = (await client.get("/bot-admin"))
    assert page.status_code == 200 and "/bot-admin/admin.js?v=" in page.text, page.text[:200]
    assert (await client.get("/bot-admin/admin.css")).headers["content-type"].startswith("text/css")
    assert (await client.get("/bot-admin/secret.py")).status_code == 404
    assert (await client.get("/bot-admin/api/me")).status_code == 401
    assert (await client.get("/bot-admin/api/me", headers=player)).status_code == 403
    me = (await client.get("/bot-admin/api/me", headers=helper)).json()
    assert [s["key"] for s in me["sections"]] == ["people", "reports"], me
    assert (await client.get("/bot-admin/api/promo", headers=helper)).status_code == 403
    me = (await client.get("/bot-admin/api/me", headers=dev)).json()
    assert [s["key"] for s in me["sections"]] == ["people", "reports", "metrics", "journal", "broadcast", "promo", "switches", "settings", "health"] and me["creator"], me

    opts = (await client.get("/bot-admin/api/promo-options", headers=dev)).json()
    skin = opts["skins"][0]["id"]
    from core.skins_v3_catalog import SKINS
    ids = [x["id"] for x in opts["skins"]] + [x["id"] for x in opts["private_skins"]]
    assert sorted(ids) == sorted(SKINS), "в выборе должны быть все образы: обычные и личные"
    assert all(x["exclusive"] for x in opts["private_skins"]) and not any(x["exclusive"] for x in opts["skins"])
    assert [x["tier"] for x in opts["skins"]][0] == "D" and [x["tier"] for x in opts["skins"]][-1] == "SSS"   # по редкости
    assert opts["skins"][0]["items"]["title"] and opts["skins"][0]["tokens"]["--v3-acc"], opts["skins"][0]
    chats = (await client.get("/bot-admin/api/chats?q=основ", headers=dev)).json()["items"]
    assert chats == [{"id": -100, "title": "Основной чат"}], chats

    body = {"code": "spring-25", "max_activations": 2, "allowed_chats": [-100], "note": "весна",
            "rewards": [{"type": "mora", "amount": 500}, {"type": "essence", "amount": 20},
                        {"type": "vip", "days": 3}, {"type": "skin", "id": skin}]}
    r = (await client.post("/bot-admin/api/promo", headers=dev, json=body))
    assert r.status_code == 200, r.text
    assert r.json()["code"] == "SPRING-25" and r.json()["rewards_text"][0] == "🪙 500 мора", r.json()
    assert (await client.post("/bot-admin/api/promo", headers=dev, json=body)).json()["detail"] == "Такой код уже есть."
    # Зарники в промокоде: только создатель; код работает как остальные и пишется в учёт отдельной причиной
    coder = {"x-session-token": create_session_token(2005)}
    assert "zarniki" in [x["type"] for x in opts["rewards"]]
    assert "zarniki" not in [x["type"] for x in (await client.get("/bot-admin/api/promo-options", headers=coder)).json()["rewards"]]
    zar = {"code": "ZAR-GIFT", "max_activations": 1, "rewards": [{"type": "zarniki", "amount": 150}, {"type": "mora", "amount": 10}]}
    r = await client.post("/bot-admin/api/promo", headers=coder, json=zar)
    assert r.status_code == 400 and "только создатель" in r.json()["detail"], r.text
    assert (await client.post("/bot-admin/api/promo/bulk", headers=coder, json={"count": 2, "rewards": zar["rewards"]})).status_code == 400
    r = await client.post("/bot-admin/api/promo", headers=dev, json=zar)
    assert r.status_code == 200 and r.json()["rewards_text"][0] == "✨ 150 зарников", r.text
    prev = (await client.post("/bot-admin/api/promo/preview", headers=dev, json=zar)).json()
    assert any("платная валюта" in w for w in prev["warnings"]) and any("Крупная награда" in w and "зарников" in w for w in prev["warnings"]), prev
    bad = {**zar, "code": "ZAR-BAD", "rewards": [{"type": "zarniki", "amount": 1.5}]}
    assert "целое" in (await client.post("/bot-admin/api/promo", headers=dev, json=bad)).json()["detail"]
    bad = {**zar, "code": "ZAR-BIG", "rewards": [{"type": "zarniki", "amount": 10_000_000}]}
    assert (await client.post("/bot-admin/api/promo", headers=dev, json=bad)).status_code == 400
    r = await client.put("/bot-admin/api/promo/ZAR-GIFT", headers=coder, json={**zar, "note": "правка"})
    assert r.status_code == 400 and "только создатель" in r.json()["detail"], r.text
    bad = {**body, "code": "FRAC", "rewards": [{"type": "mora", "amount": 1.5}]}
    assert "целое" in (await client.post("/bot-admin/api/promo", headers=dev, json=bad)).json()["detail"]
    bad = {**body, "code": "x"}
    assert "3–32" in (await client.post("/bot-admin/api/promo", headers=dev, json=bad)).json()["detail"]
    r = (await client.post("/bot-admin/api/promo", headers=dev, json={
        "code": "OLDTIME", "rewards": [{"type": "diamonds", "amount": "2.5"}], "valid_until": "2020-01-01T00:00:00Z"}))
    assert r.status_code == 200 and r.json()["rewards_text"] == ["💎 2.50 алмазы"], r.text
    return client, dev


async def redeem_checks():
    from infrastructure.database import get_pool
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import skins_v3 as skins_v3_repo
    from bot.chat import registry
    from bot.chat.framework import dispatch
    from services import promo_v2

    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)

        async def say(text, uid, chat=-100):
            m = FakeMessage(text, uid, chat)
            await dispatch(registry, m, FakeBot(), db)
            return " | ".join(m.replies)

        assert "только персоналу" in await say("бот админка", 2002)
        os.environ["MINIAPP_URL"] = "https://example.test/predvestnik/?startapp=x"
        m = FakeMessage("бот админка", 1001, chat=1001)
        replies = []
        async def reply(text, **kw):
            replies.append((text, kw))
        m.reply = reply
        await dispatch(registry, m, FakeBot(), db)
        btn = replies[0][1]["reply_markup"].inline_keyboard[0][0]
        assert btn.web_app.url == "https://example.test/predvestnik/bot-admin", btn

        out = await say("бот промокод spring-25", 2002)
        assert "активирован" in out and "500 мора" in out and "эссенции" in out and "VIP на 3" in out, out
        out = await say("бот промокод SPRING-25", 2002)
        assert "уже активировали" in out, out
        out = await say("бот промокод SPRING-25", 2003, chat=-200)
        assert "определённых чатах" in out, out
        out = await say("бот промокод SPRING-25", 2003, chat=2003)                     # личка — тоже не тот чат
        assert "определённых чатах" in out, out
        out = await say("бот промокод SPRING-25", 2004)
        assert "активирован" in out, out
        out = await say("бот промокод SPRING-25", 2005)
        assert "закончились активации" in out, out
        out = await say("бот промокод NOPE", 2005)
        assert "нет или он выключен" in out, out
        out = await say("бот промокод OLDTIME", 2005)
        assert "закончился" in out, out
        out = await say("бот промокод", 2005)
        assert "Формат" in out, out

        out = await say("бот промокод zar-gift", 2003)
        assert "активирован" in out and "150 зарников" in out, out
        out = await say("бот промокод ZAR-GIFT", 2004)
        assert "закончились активации" in out, out
        async with db.execute("SELECT user_balance_zarniki FROM users WHERE user_tg_id = 2003") as cur:
            assert float((await cur.fetchone())[0]) == 150
        async with db.execute("SELECT reason_code, delta FROM economic_ledger WHERE user_id = 2003 AND currency = 'zarniki'") as cur:
            assert [(r[0], int(r[1])) for r in await cur.fetchall()] == [("promocode_zarniki", 150)]
        async with db.execute("SELECT user_balance_mora FROM users WHERE user_tg_id = 2002") as cur:
            assert float((await cur.fetchone())[0]) == 500
        assert await skins_v3_repo.essence_balance(db, 2002) == 20
        async with db.execute("SELECT expires_at > NOW() + INTERVAL '2 days' FROM vip_subscriptions "
                              "WHERE user_id = 2002") as cur:
            assert (await cur.fetchone())[0]
        assert len(await skins_v3_repo.owned(db, 2002)) == 1

        # Старый формат: награды в старых колонках — не активируется, пока не пересохранят.
        await db.execute("INSERT INTO promocodes (code, reward_mora, is_active) VALUES ('LEGACY1', 100, 1)")
        try:
            await promo_v2.redeem(db, user_id=2005, code="legacy1", chat_id=-100)
            raise AssertionError("legacy code redeemed")
        except promo_v2.PromoError as exc:
            assert "старого формата" in str(exc)
        async with db.execute("SELECT COUNT(*) FROM promocode_redemptions WHERE code = 'LEGACY1'") as cur:
            assert (await cur.fetchone())[0] == 0                                       # отказ ничего не записал


async def private_checks(client, dev):
    """Личные образы через промокод: один владелец, поэтому промокод одноразовый или именной."""
    from infrastructure.database import get_pool
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import skins_v3 as skins_v3_repo
    from bot.chat import registry
    from bot.chat.framework import dispatch
    opts = (await client.get("/bot-admin/api/promo-options", headers=dev)).json()
    sid, other = opts["private_skins"][0]["id"], opts["private_skins"][1]["id"]
    assert all(x["holders"] == [] for x in opts["private_skins"]), opts["private_skins"]
    skin = {"type": "skin", "id": sid}

    async def create(code, **kw):
        return await client.post("/bot-admin/api/promo", headers=dev, json={"code": code, "rewards": [skin], **kw})

    r = await create("PRIV-OPEN")
    assert r.status_code == 400 and "на одного владельца" in r.json()["detail"], r.text
    r = await create("PRIV-MANY", max_activations=3)
    assert r.status_code == 400, r.text
    r = await create("PRIV-1", max_activations=1)
    assert r.status_code == 200 and r.json()["rewards_text"][0].startswith("🌟 личный образ"), r.text
    assert (await create("PRIV-2", max_activations=1)).status_code == 200                # пока образ свободен, можно
    named = await client.post("/bot-admin/api/promo", headers=dev, json={
        "code": "PRIV-NAMED", "allowed_users": [2004], "rewards": [{"type": "skin", "id": other}]})
    assert named.status_code == 200, named.text

    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)

        async def say(text, uid):
            m = FakeMessage(text, uid, -100)
            await dispatch(registry, m, FakeBot(), db)
            return " | ".join(m.replies)

        out = await say("бот промокод PRIV-1", 2002)
        assert "активирован" in out and "личный образ" in out, out
        assert [h["user_id"] for h in await skins_v3_repo.holders(db, sid)] == [2002]
        out = await say("бот промокод PRIV-2", 2004)                                     # образ уже ушёл
        assert "уже достался другому игроку" in out and "2002" not in out and "@u2002" not in out, out
        async with db.execute("SELECT (SELECT COUNT(*) FROM promocode_redemptions WHERE code = 'PRIV-2'), "
                              "(SELECT activations_count FROM promocodes WHERE code = 'PRIV-2')") as cur:
            assert tuple(await cur.fetchone()) == (0, 0)                                  # отказ ничего не записал
        out = await say("бот промокод PRIV-NAMED", 2005)
        assert "не для вас" in out, out
        assert "активирован" in await say("бот промокод PRIV-NAMED", 2004)

    r = await create("PRIV-3", max_activations=1)                                         # занятый образ в новый код не кладётся
    assert r.status_code == 400 and "уже у" in r.json()["detail"] and "отзовите" in r.json()["detail"], r.text
    opts = (await client.get("/bot-admin/api/promo-options", headers=dev)).json()
    held = next(x for x in opts["private_skins"] if x["id"] == sid)
    assert [h["user_id"] for h in held["holders"]] == [2002], held
    r = await client.put("/bot-admin/api/promo/priv-1", headers=dev, json={
        "rewards": [skin], "max_activations": 1, "note": "выдан", "is_active": True})  # уже использованный код правится
    assert r.status_code == 200 and r.json()["note"] == "выдан", r.text


async def after_checks(client, dev):
    p = (await client.get("/bot-admin/api/promo/spring-25", headers=dev)).json()
    assert p["activations"] == 2 and len(p["redemptions"]) == 2, p
    assert p["redemptions"][0]["chat_title"] == "Основной чат" and p["redemptions"][0]["granted"], p
    listed = (await client.get("/bot-admin/api/promo?q=", headers=dev)).json()["items"]
    assert {x["code"] for x in listed} >= {"SPRING-25", "OLDTIME", "LEGACY1"}
    assert next(x for x in listed if x["code"] == "LEGACY1")["legacy"]
    r = (await client.post("/bot-admin/api/promo/spring-25/active", headers=dev, json={"active": False}))
    assert r.status_code == 200 and not r.json()["is_active"]
    r = (await client.put("/bot-admin/api/promo/legacy1", headers=dev, json={"rewards": [{"type": "mora", "amount": 100}]}))
    assert r.status_code == 200 and not r.json()["legacy"], r.text

    # Журнал: промокоды, выключатели и настройки пишутся в общую ленту, у неё есть фильтры и «ещё»
    assert (await client.post("/bot-admin/api/switches", headers=dev, json={"feature": "group:warps", "enabled": False})).status_code == 200
    assert (await client.post("/bot-admin/api/settings/transfer", headers=dev, json={"currencies": ["mora"]})).status_code == 200
    feed = (await client.get("/bot-admin/api/journal?days=1", headers=dev)).json()
    titles = [x["title"] for x in feed["items"]]
    assert {"Промокод создан", "Промокод изменён", "Промокод включён или выключен", "Выключатель", "Валюты для переводов"} <= set(titles), titles
    texts = {x["title"]: x["text"] for x in feed["items"]}
    assert texts["Выключатель"] == "group:warps везде → выключено" and texts["Валюты для переводов"] == "mora", texts
    assert any(x["text"].endswith("выключен") for x in feed["items"] if x["title"].startswith("Промокод включён")), feed["items"]
    only = (await client.get("/bot-admin/api/journal?kind=promo&days=1", headers=dev)).json()
    assert {x["kind"] for x in only["items"]} == {"promo"} and [k["key"] for k in only["kinds"]][0] == "moderation", only["kinds"]
    page = (await client.get("/bot-admin/api/journal?kind=promo&days=1&limit=1", headers=dev)).json()
    assert page["actors"] and all("id" in a for a in page["actors"]), page["actors"]
    nobody = (await client.get("/bot-admin/api/journal?actor=424242&days=1", headers=dev)).json()
    assert nobody["items"] == [] and not nobody["more"], nobody
    from FastAPI.auth import create_session_token
    assert (await client.get("/bot-admin/api/journal", headers={"x-session-token": create_session_token(3003)})).status_code == 403


async def insight_checks(client, dev):
    """Статистика кода, предпросмотр для админа, предупреждения о дорогом и пачка одноразовых кодов."""
    p = (await client.get("/bot-admin/api/promo/spring-25", headers=dev)).json()
    st = p["stats"]
    assert (st["activations"], st["limit"], st["left"], st["chats"], st["private"]) == (2, 2, 0, 1, 0), st
    assert st["spent"] == {"mora": "1000", "essence": "40", "vip_days": "6"}, st
    assert len(st["per_day"]) == 14 and st["per_day"][-1]["n"] == 2 and sum(d["n"] for d in st["per_day"]) == 2, st["per_day"]
    assert st["first_at"] and st["last_at"], st

    # Предпросмотр ничего не сохраняет и не требует кода
    r = await client.post("/bot-admin/api/promo/preview", headers=dev, json={
        "rewards": [{"type": "mora", "amount": 500}, {"type": "vip", "days": 3}], "max_activations": 10})
    assert r.status_code == 200, r.text
    pv = r.json()
    assert pv["code"] == "КОД" and pv["player_text"] == ["🪙 500 мора", "👑 VIP на 3 дн."], pv
    assert "любого игрока" in pv["who_can"] and pv["warnings"] == [], pv
    r = await client.post("/bot-admin/api/promo/preview", headers=dev, json={
        "code": "big-one", "rewards": [{"type": "mora", "amount": 250000}], "allowed_chats": [-100]})
    pv = r.json()
    assert pv["code"] == "BIG-ONE" and "выбранных чатах" in pv["who_can"], pv
    assert any("Крупная награда на одного игрока: 250 000 мора" in w for w in pv["warnings"]) and any("Нет лимита" in w for w in pv["warnings"]), pv
    r = await client.post("/bot-admin/api/promo/preview", headers=dev, json={
        "rewards": [{"type": "diamonds", "amount": 2}], "max_activations": 100, "valid_until": "2099-01-01T00:00:00Z"})
    assert r.json()["warnings"] == [], r.json()
    r = await client.post("/bot-admin/api/promo/preview", headers=dev, json={
        "rewards": [{"type": "diamonds", "amount": 2}], "max_activations": 100})
    assert r.json()["warnings"] == [], r.json()
    r = await client.post("/bot-admin/api/promo/preview", headers=dev, json={
        "rewards": [{"type": "diamonds", "amount": 10}], "max_activations": 100000})
    assert any("за весь лимит" in w for w in r.json()["warnings"]), r.json()
    assert (await client.post("/bot-admin/api/promo/preview", headers=dev, json={"rewards": []})).status_code == 400
    assert (await client.post("/bot-admin/api/promo/preview", headers=dev, json={
        "rewards": [{"type": "mora", "amount": 1.5}]})).status_code == 400
    async with __import__("infrastructure.database", fromlist=["get_pool"]).get_pool().acquire() as conn:
        n = await conn.fetchval("SELECT COUNT(*) FROM promocodes WHERE code IN ('BIG-ONE', 'КОД')")
    assert n == 0, "предпросмотр ничего не сохраняет"

    # Пачка одноразовых кодов
    reward = [{"type": "mora", "amount": 100}, {"type": "diamonds", "amount": 1}]
    r = await client.post("/bot-admin/api/promo/bulk", headers=dev, json={"prefix": "evt", "count": 25, "rewards": reward})
    assert r.status_code == 200, r.text
    made = r.json()
    codes = made["codes"]
    assert len(codes) == 25 == len(set(codes)) and all(c.startswith("EVT-") and len(c) == 12 for c in codes), codes[:3]
    assert made["rewards_text"][0] == "🪙 100 мора" and len(made["rewards_text"]) == 2, made
    one = (await client.get(f"/bot-admin/api/promo/{codes[0].lower()}", headers=dev)).json()
    assert one["max_activations"] == 1 and one["is_active"] and one["note"] == "Пачка из 25 одноразовых кодов", one
    assert one["stats"]["left"] == 1, one["stats"]
    r = await client.post("/bot-admin/api/promo/bulk", headers=dev, json={"count": 3, "rewards": reward})
    assert r.status_code == 200 and all(len(c) == 8 and "-" not in c for c in r.json()["codes"]), r.text   # без начала — просто случайные
    # Границы и отказы: ничего не остаётся наполовину
    for bad, text in (({"count": 0}, "от 1 до 200"), ({"count": 201}, "от 1 до 200"), ({"count": "abc"}, "целое число"),
                      ({"count": 5, "prefix": "x" * 17}, "до 16 символов"), ({"count": 5, "prefix": "a b"}, "до 16 символов"),
                      ({"count": 5, "allowed_users": [2002]}, "не привязывается"), ({"count": 5, "rewards": []}, "")):
        r = await client.post("/bot-admin/api/promo/bulk", headers=dev, json={"prefix": "bad", "rewards": reward, **bad})
        assert r.status_code == 400 and text in r.json()["detail"], (bad, r.text)
    opts = (await client.get("/bot-admin/api/promo-options", headers=dev)).json()
    r = await client.post("/bot-admin/api/promo/bulk", headers=dev, json={
        "prefix": "skn", "count": 2, "rewards": [{"type": "skin", "id": opts["private_skins"][0]["id"]}]})
    assert r.status_code == 400 and "нельзя раздавать пачкой" in r.json()["detail"], r.text
    async with __import__("infrastructure.database", fromlist=["get_pool"]).get_pool().acquire() as conn:
        left = await conn.fetchval("SELECT COUNT(*) FROM promocodes WHERE code LIKE 'BAD-%' OR code LIKE 'SKN-%'")
    assert left == 0, "отказ не оставляет часть кодов"

    # Пачку активирует игрок как обычный код, второй раз тот же код уже не сработает
    from infrastructure.database import get_pool
    from infrastructure.pg_adapter import PGAdapter
    from services import promo_v2
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        got = await promo_v2.redeem(db, user_id=2002, code=codes[1], chat_id=-100)
        assert got.granted == made["rewards_text"], got
        try:
            await promo_v2.redeem(db, user_id=2003, code=codes[1], chat_id=-100)
            raise AssertionError("one-shot code redeemed twice")
        except promo_v2.PromoError as exc:
            assert "закончились активации" in str(exc), exc
    audit = (await client.get("/bot-admin/api/journal?kind=promo&days=1", headers=dev)).json()["items"]
    row = next(x for x in audit if x["title"] == "Пачка промокодов создана" and "25 шт." in x["text"])
    assert "EVT-" in row["text"], row


async def disabled_check():
    from infrastructure.database import get_pool
    from infrastructure.pg_adapter import PGAdapter
    from services import promo_v2
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        try:
            await promo_v2.redeem(db, user_id=2005, code="SPRING-25", chat_id=-100)
            raise AssertionError("disabled code redeemed")
        except promo_v2.PromoError as exc:
            assert "выключен" in str(exc)
        result = await promo_v2.redeem(db, user_id=2005, code="LEGACY1", chat_id=None)
        assert result.granted == ["🪙 100 мора"], result
        legacy = (await promo_v2.get_code(db, "LEGACY1"))["stats"]
        assert (legacy["activations"], legacy["private"], legacy["chats"]) == (1, 1, 0), legacy   # личка: чата нет


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(prepare())
    client, dev = loop.run_until_complete(http_checks())
    loop.run_until_complete(redeem_checks())
    loop.run_until_complete(private_checks(client, dev))
    loop.run_until_complete(after_checks(client, dev))
    loop.run_until_complete(insight_checks(client, dev))
    loop.run_until_complete(disabled_check())
    print("OK: bot admin and promo codes on PostgreSQL")


main()
