"""Админка: подтверждение ID для опасных действий, лимиты частоты, журнал входов, завершение сессий и тревоги владельцу.

Запуск: python tools/test_bot_admin_security_pg.py --dsn postgresql://... (пустая тестовая БД!)
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
PHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Telegram"
LAPTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36"


class FakeBot:
    def __init__(self):
        self.calls = []

    async def me(self):
        return SimpleNamespace(id=999, username="predvestnik_bot")

    async def ban_chat_member(self, chat_id, user_id, until_date=None):
        self.calls.append(("ban", chat_id, user_id))

    async def unban_chat_member(self, chat_id, user_id, only_if_banned=False):
        self.calls.append(("unban", chat_id, user_id))

    async def restrict_chat_member(self, chat_id, user_id, permissions=None, until_date=None):
        self.calls.append(("restrict", chat_id, user_id))

    async def get_chat(self, chat_id):
        return SimpleNamespace(permissions=None)

    async def send_message(self, chat_id, text, **kw):
        self.calls.append(("send", chat_id, text))

    def alerts(self, to=DEV):
        return [c[2] for c in self.calls if c[0] == "send" and c[1] == to and "Админка: необычное действие" in c[2]]


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
        for uid, rank in ((DEV, 0), (HELPER, 3), (SENIOR, 4), (CODER, 5), (P1, 0), (P2, 0)):
            await db.execute("INSERT INTO users (user_tg_id, user_tg_username, bot_rank) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                             (uid, f"u{uid}", rank))
        for chat, title in ((-100, "Основной чат"), (-200, "Другой чат")):
            await db.execute("INSERT INTO chat_settings (chat_id, chat_title) VALUES (?, ?) ON CONFLICT DO NOTHING", (chat, title))
        for uid, chat in ((P1, -100), (P1, -200), (P2, -100), (SENIOR, -100)):
            await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, user_messages_count_all_time, is_left, last_message_at) "
                             "VALUES (?, ?, 5, FALSE, NOW())", (uid, chat))


class Client:
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
    from services import admin_security as sec

    bot = FakeBot()
    people.set_bot(bot)
    client = Client(main.app)
    h = {uid: {"x-session-token": create_session_token(uid)} for uid in (DEV, HELPER, SENIOR, CODER, P1)}

    async def act(who, uid, **body):
        return await client.post(f"/bot-admin/api/player/{uid}/action", headers=h[who], json=body)

    async def scalar(sql, *args):
        async with get_pool().acquire() as conn:
            async with PGAdapter(conn).execute(sql, args) as cur:
                return (await cur.fetchone())[0]

    # ── Подтверждение ID ──
    card = (await client.get(f"/bot-admin/api/player/{P1}", headers=h[CODER])).json()
    assert card["confirm_rules"]["actions"] == ["global_ban", "rank", "skin_revoke"] and card["confirm_rules"]["balance"]["mora"] == 100000, card["confirm_rules"]
    r = await act(CODER, P1, action="global_ban", reason="спам")
    assert r.status_code == 400 and "введите ID" in r.json()["detail"], r.text
    r = await act(CODER, P1, action="global_ban", reason="спам", confirm="2003")
    assert r.status_code == 400, r.text                                     # чужой ID
    assert not [c for c in bot.calls if c[0] == "ban"], bot.calls            # до подтверждения никого не банили
    r = await act(CODER, P1, action="global_ban", reason="спам", confirm=str(P1))
    assert r.status_code == 200 and ("ban", -100, P1) in bot.calls, (r.status_code, r.text)
    r = await act(CODER, P2, action="rank", rank=2, reason="повышение")
    assert r.status_code == 400, r.text
    r = await act(CODER, P2, action="rank", rank=2, reason="повышение", confirm=f"@{'u2003'.upper()}")   # @ник без учёта регистра
    assert r.status_code == 200, r.text
    assert await scalar("SELECT bot_rank FROM users WHERE user_tg_id = ?", P2) == 2
    # Небольшие суммы без подтверждения, крупные — с ним
    r = await act(CODER, P1, action="balance", currency="mora", amount="500", reason="приз")
    assert r.status_code == 200, r.text
    r = await act(CODER, P1, action="balance", currency="mora", amount="100000", reason="большой приз")
    assert r.status_code == 400 and "введите ID" in r.json()["detail"], r.text
    r = await act(CODER, P1, action="balance", currency="diamonds", amount="100", reason="приз")
    assert r.status_code == 400 and "введите ID" in r.json()["detail"], r.text
    r = await act(CODER, P1, action="balance", currency="diamonds", amount="100", reason="приз", confirm=str(P1))
    assert r.status_code == 200, r.text
    r = await act(CODER, P1, action="balance", currency="diamonds", amount="99", reason="приз")
    assert r.status_code == 200, r.text
    # Вспомогательные функции
    assert sec.confirmed(5, "Bob", {"confirm": " @bob "}) and sec.confirmed(5, None, {"confirm": "5"})
    assert not sec.confirmed(5, "bob", {"confirm": ""}) and not sec.confirmed(5, None, {"confirm": "x"})
    assert not sec.needs_confirm("balance", {"currency": "mora", "amount": "abc"}) and not sec.needs_confirm("mute", {})

    # ── Тревоги владельцу ──
    await sec.drain()
    alerts = "\n".join(bot.alerts(DEV))
    assert "забанил" in alerts and "изменил роль" in alerts and "@u5005" in alerts, alerts   # CODER: бан во всех чатах и роль
    assert bot.alerts(CODER) == [], "автору действия тревога не нужна"
    big = [a for a in bot.alerts(DEV) if "изменил баланс" in a]
    assert len(big) == 1 and " 100" in big[0], big                         # только крупная сумма: не 500 мор и не 99 алмазов
    before = len(bot.alerts(DEV))
    r = await act(DEV, P2, action="rank", rank=3, reason="создатель", confirm=str(P2))
    assert r.status_code == 200, r.text
    await sec.drain()
    assert len(bot.alerts(DEV)) == before, "действия самого владельца тревогу не поднимают"

    # Пачка важных действий за 10 минут (порог ради теста ниже)
    sec.BURST_COUNT = 4
    sec.reset_limits()
    n0 = len(bot.alerts(DEV))
    for i in range(1, 5):
        r = await act(CODER, P1, action="vip", days=1, reason=f"vip {i}")
        assert r.status_code == 200, r.text
    await sec.drain()
    burst = [a for a in bot.alerts(DEV)[n0:] if "важных действий" in a]
    assert len(burst) == 1, bot.alerts(DEV)[n0:]
    r = await act(CODER, P1, action="vip", days=1, reason="ещё")
    await sec.drain()
    assert len([a for a in bot.alerts(DEV)[n0:] if "важных действий" in a]) == 1, "повторная тревога чаще раза в 30 минут не нужна"
    sec.BURST_COUNT = 10

    # ── Лимиты частоты ──
    sec.reset_limits()
    assert sec.rate_wait(77, 3, "moderation", now=0) == 0
    sec.LIMITS["moderation"] = (3, 300)
    sec.reset_limits()
    for i in range(3):
        assert sec.rate_wait(77, 3, "moderation", now=i) == 0
    wait = sec.rate_wait(77, 3, "moderation", now=10)
    assert 285 <= wait <= 295, wait
    assert sec.rate_wait(77, 3, "moderation", now=301) == 0 and sec.rate_wait(77, 3, "moderation", now=302) == 0   # окно сдвинулось
    assert all(sec.rate_wait(1001, 6, "moderation", now=0) == 0 for _ in range(50))   # создатель без лимита
    sec.reset_limits()
    for i in range(3):
        r = await act(SENIOR, P1, action="mute", chat_id=-100, minutes=5, reason=f"m{i}")
        assert r.status_code == 200, r.text
    r = await act(SENIOR, P1, action="mute", chat_id=-100, minutes=5, reason="четвёртый")
    assert r.status_code == 429 and "Слишком много действий" in r.json()["detail"], r.text
    r = await act(HELPER, P1, action="mute", chat_id=-100, minutes=5)     # лимит у каждого свой
    assert r.status_code == 200, r.text
    for i in range(6):
        r = await act(DEV, P1, action="mute", chat_id=-100, minutes=5)
        assert r.status_code == 200, r.text
    r = await client.post("/bot-admin/api/chat/-100/action", headers=h[SENIOR], json={"action": "close"})
    assert r.status_code == 429, r.text                                   # действия в чате считаются в тот же лимит
    sec.LIMITS["moderation"] = (60, 300)
    sec.LIMITS["sensitive"] = (2, 3600)
    sec.reset_limits()
    for i in range(2):
        assert (await act(CODER, P1, action="vip", days=1, reason=f"v{i}")).status_code == 200
    assert (await act(CODER, P1, action="vip", days=1, reason="v3")).status_code == 429
    assert (await act(DEV, P1, action="vip", days=1, reason="v3")).status_code == 200
    bulk = await client.post("/bot-admin/api/players/bulk", headers=h[CODER],
                             json={"ids": [P1, P2], "action": "mark_grant", "mark": "x", "reason": "тест"})
    assert bulk.status_code == 429, bulk.text                             # пачка из двух = два засчитанных действия
    sec.LIMITS["sensitive"] = (60, 3600)
    sec.reset_limits()

    # ── Журнал входов ──
    me = lambda who, ua: client.get("/bot-admin/api/me", headers={**h[who], "user-agent": ua, "x-forwarded-for": "203.0.113.7, 10.0.0.1"})
    n0 = len(bot.alerts(DEV))
    assert (await me(SENIOR, PHONE)).status_code == 200
    assert (await me(SENIOR, PHONE)).status_code == 200                   # тот же вход за полчаса не дублируется
    await sec.drain()
    assert await scalar("SELECT COUNT(*) FROM bot_admin_logins WHERE user_id = ?", SENIOR) == 1
    assert len(bot.alerts(DEV)) == n0, "первый вход — не новое устройство"
    assert (await me(SENIOR, LAPTOP)).status_code == 200
    await sec.drain()
    assert await scalar("SELECT COUNT(*) FROM bot_admin_logins WHERE user_id = ?", SENIOR) == 2
    fresh = bot.alerts(DEV)[n0:]
    assert len(fresh) == 1 and "нового устройства" in fresh[0] and "Windows · Chrome" in fresh[0], fresh
    assert (await me(DEV, LAPTOP)).status_code == 200 and (await me(DEV, PHONE)).status_code == 200
    await sec.drain()
    assert len(bot.alerts(DEV)) == n0 + 1, "владельца о его же устройствах не тревожим"
    assert await scalar("SELECT ip FROM bot_admin_logins WHERE user_id = ? ORDER BY id LIMIT 1", SENIOR) == "203.0.113.7"
    assert sec.device_label(PHONE, "telegram") == "iPhone · Telegram" and sec.device_label("", "") == "устройство · браузер"
    # Журнал входов видит только создатель
    assert (await client.get("/bot-admin/api/logins", headers=h[SENIOR])).status_code == 403
    assert (await client.get("/bot-admin/api/logins", headers=h[CODER])).status_code == 403
    logins = (await client.get("/bot-admin/api/logins?days=7", headers=h[DEV])).json()["items"]
    assert {x["user"]["id"] for x in logins} == {SENIOR, DEV} and logins[0]["device"] and logins[0]["at"], logins
    only = (await client.get(f"/bot-admin/api/logins?user_id={SENIOR}", headers=h[DEV])).json()["items"]
    assert len(only) == 2 and all(x["user"]["id"] == SENIOR for x in only) and only[0]["ip"] == "203.0.113.7", only

    # ── Завершение сессий ──
    old = {uid: create_session_token(uid) for uid in (HELPER, SENIOR, DEV)}
    hdr = lambda tok: {"x-session-token": tok}
    for tok in old.values():
        assert (await client.get("/bot-admin/api/me", headers=hdr(tok))).status_code == 200
    await asyncio.sleep(1.2)   # время в токене — целые секунды
    # свои сессии: любой сотрудник, у остальных всё работает
    r = await client.post("/bot-admin/api/sessions/revoke", headers=hdr(old[SENIOR]), json={})
    assert r.status_code == 200 and "заново" in r.json()["message"], r.text
    assert (await client.get("/bot-admin/api/me", headers=hdr(old[SENIOR]))).status_code == 401
    assert (await client.get("/bot-admin/api/me", headers=hdr(old[HELPER]))).status_code == 200
    await asyncio.sleep(1.2)
    fresh_senior = create_session_token(SENIOR)
    assert (await client.get("/bot-admin/api/me", headers=hdr(fresh_senior))).status_code == 200      # новый вход работает
    # чужие сессии — только создатель (действие «завершить сессии» у игрока)
    assert (await act(CODER, SENIOR, action="revoke_sessions")).status_code == 403
    assert (await act(DEV, HELPER, action="revoke_sessions")).status_code == 200
    assert (await client.get("/bot-admin/api/me", headers=hdr(old[HELPER]))).status_code == 401
    assert (await client.get("/bot-admin/api/me", headers=hdr(fresh_senior))).status_code == 200
    # все сотрудники — только создатель
    assert (await client.post("/bot-admin/api/sessions/revoke", headers=hdr(fresh_senior), json={"all": True})).status_code == 403
    await asyncio.sleep(1.2)
    assert (await client.post("/bot-admin/api/sessions/revoke", headers=hdr(old[DEV]), json={"all": True})).status_code == 200
    for who in (SENIOR, DEV):
        tok = fresh_senior if who == SENIOR else old[DEV]
        r = await client.get("/bot-admin/api/me", headers=hdr(tok))
        assert r.status_code == 401 and "Откройте админку заново" in r.json()["detail"], (who, r.text)
    await asyncio.sleep(1.2)
    assert (await client.get("/bot-admin/api/me", headers=hdr(create_session_token(DEV)))).status_code == 200
    # initData после завершения: старый вход (auth_date до отзыва) не проходит, новый — проходит
    import hashlib
    import hmac
    import json
    import time
    from urllib.parse import urlencode

    def init_data(uid, auth_date):
        user = json.dumps({"id": uid, "first_name": "T"}, separators=(",", ":"))
        pairs = {"auth_date": str(auth_date), "query_id": "q", "user": user}
        check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", os.environ["BOT_TOKEN"].encode(), hashlib.sha256).digest()
        return urlencode({**pairs, "hash": hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()})

    stale, current = init_data(HELPER, int(time.time()) - 60), init_data(HELPER, int(time.time()))
    r = await client.get("/bot-admin/api/me", headers={"x-init-data": stale})
    assert r.status_code == 401, "initData, выданный до «завершить сессии всех», не должен проходить"
    r = await client.get("/bot-admin/api/me", headers={"x-init-data": current})
    assert r.status_code == 200, r.text
    # Журнал действий знает про завершение сессий
    jr = (await client.get("/bot-admin/api/journal?days=1", headers=hdr(create_session_token(DEV)))).json()
    titles = [x["title"] for x in jr["items"]]
    assert "Завершены сессии админки" in titles, titles


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(prepare())
    loop.run_until_complete(checks())
    print("OK: bot admin security (typed confirm, rate limits, login journal, session revoke, owner alerts) on PostgreSQL")


main()
