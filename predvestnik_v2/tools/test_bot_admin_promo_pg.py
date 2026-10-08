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
    assert [s["key"] for s in me["sections"]] == ["people"], me
    assert (await client.get("/bot-admin/api/promo", headers=helper)).status_code == 403
    me = (await client.get("/bot-admin/api/me", headers=dev)).json()
    assert [s["key"] for s in me["sections"]] == ["people", "promo", "switches", "settings"] and me["creator"], me

    opts = (await client.get("/bot-admin/api/promo-options", headers=dev)).json()
    skin = opts["skins"][0]["id"]
    chats = (await client.get("/bot-admin/api/chats?q=основ", headers=dev)).json()["items"]
    assert chats == [{"id": -100, "title": "Основной чат"}], chats

    body = {"code": "spring-25", "max_activations": 2, "allowed_chats": [-100], "note": "весна",
            "rewards": [{"type": "mora", "amount": 500}, {"type": "essence", "amount": 20},
                        {"type": "vip", "days": 3}, {"type": "skin", "id": skin}]}
    r = (await client.post("/bot-admin/api/promo", headers=dev, json=body))
    assert r.status_code == 200, r.text
    assert r.json()["code"] == "SPRING-25" and r.json()["rewards_text"][0] == "🪙 500 мора", r.json()
    assert (await client.post("/bot-admin/api/promo", headers=dev, json=body)).json()["detail"] == "Такой код уже есть."
    bad = {**body, "code": "ZAR", "rewards": [{"type": "zarniki", "amount": 5}]}
    assert "Зарники" in (await client.post("/bot-admin/api/promo", headers=dev, json=bad)).json()["detail"]
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


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(prepare())
    client, dev = loop.run_until_complete(http_checks())
    loop.run_until_complete(redeem_checks())
    loop.run_until_complete(after_checks(client, dev))
    loop.run_until_complete(disabled_check())
    print("OK: bot admin and promo codes on PostgreSQL")


main()
