"""Админка: исправления по поиску багов — журнал, жалобы, рассылки, кривые данные в запросах.

Запуск: python tools/test_bot_admin_review_pg.py --dsn postgresql://... (пустая тестовая БД!)
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

DEV, HELPER, SENIOR, CODER, P1, P2, P3, GONE = 1001, 3003, 4004, 5005, 2002, 2003, 2004, 2005


class FakeBot:
    def __init__(self):
        self.sent = []
        self.delay = 0.0

    async def me(self):
        return SimpleNamespace(id=999, username="predvestnik_bot")

    async def send_message(self, chat_id, text, **kw):
        if self.delay:
            await asyncio.sleep(self.delay)
        self.sent.append((chat_id, text))

    def __getattr__(self, name):   # restrict/ban/unban_chat_member
        async def call(*a, **kw):
            return None
        return call


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
    from bot.startup_schema import ensure_runtime_schema
    from FastAPI.auth import create_session_token
    from FastAPI.routers.bot_admin import people
    from services import admin_people, broadcasts, reports as reports_service
    import FastAPI.main as main

    await create_pool()
    await init_db()
    await ensure_runtime_schema(get_pool())
    await ensure_chat_schema()
    bot = FakeBot()
    people.set_bot(bot)
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        for uid, rank in ((DEV, 0), (HELPER, 3), (SENIOR, 4), (CODER, 5), (P1, 0), (P2, 0), (P3, 0), (GONE, 0)):
            await db.execute("INSERT INTO users (user_tg_id, user_tg_username, bot_rank) VALUES (?, ?, ?)",
                             (uid, f"u{uid}", rank))
        await db.execute("UPDATE users SET deleted_at = NOW() WHERE user_tg_id = ?", (GONE,))
        await db.execute("INSERT INTO chat_settings (chat_id, chat_title) VALUES (-100, 'Чат')")
        for uid in (P1, P2, P3):
            await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id) VALUES (?, -100)", (uid,))
        await broadcasts.ensure_schema(db)
        await reports_service.ensure_schema(db)

    client = Client(main.app)
    h = {uid: {"x-session-token": create_session_token(uid)} for uid in (DEV, HELPER, SENIOR, CODER)}
    api = "/bot-admin/api"

    # ── Журнал: «Показать ещё» отдаёт вторую страницу, а не 500 ──────────────────
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        for i in range(35):
            await admin_people.audit(db, CODER, "balance", user_id=P1, details={"currency": "mora", "amount": i + 1, "reason": f"n{i}"})
    first = (await client.get(f"{api}/journal?days=1", headers=h[SENIOR])).json()
    assert first["more"] and len(first["items"]) == 30 and first["next"], first
    from urllib.parse import quote
    r = await client.get(f"{api}/journal?days=1&before={quote(first['next'])}", headers=h[SENIOR])
    assert r.status_code == 200, r.text
    second = r.json()
    assert len(second["items"]) == 5 and not second["more"], second
    assert not ({x["at"] for x in first["items"]} & {x["at"] for x in second["items"]}), "страницы пересекаются"
    assert (await client.get(f"{api}/journal?days=1&before=мусор", headers=h[SENIOR])).status_code == 200   # битый курсор — с начала

    # ── Карточка и журнал: бан во всех чатах — одной строкой, причина в фигурных скобках не теряется ──
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        for _ in range(6):
            await db.execute("INSERT INTO moderation_logs (chat_id, user_id, admin_id, action) VALUES (-100, ?, ?, 'global_ban_chat')", (P1, CODER))
        await db.execute("INSERT INTO moderation_logs (chat_id, user_id, admin_id, action, reason) VALUES (-100, ?, ?, 'warn', '{флуд} в чате')", (P1, SENIOR))
    card = (await client.get(f"{api}/player/{P1}", headers=h[HELPER])).json()
    assert "global_ban_chat" not in {x["action"] for x in card["history"]}, card["history"]
    assert any(x["action"] == "warn" and x["reason"] == "{флуд} в чате" for x in card["history"]), card["history"]

    # ── Жалобы: два одновременных «наказать» дают одно наказание, повторное «взять» не затирает первого ──
    async with get_pool().acquire() as conn:
        rid = await reports_service.create(PGAdapter(conn), chat_id=-100, reporter_id=P2, target_id=P3, reason="спам")
    punish = lambda: client.post(f"{api}/reports/{rid}/punish", headers=h[SENIOR], json={"action": "warn", "reason": "спам"})
    got = await asyncio.gather(punish(), punish())
    assert sorted(r.status_code for r in got) == [200, 409], [r.text for r in got]
    async with get_pool().acquire() as conn:
        async with PGAdapter(conn).execute("SELECT COUNT(*) FROM user_warnings WHERE chat_id = -100 AND user_id = ?", (P3,)) as cur:
            assert (await cur.fetchone())[0] == 1
        rid2 = await reports_service.create(PGAdapter(conn), chat_id=-100, reporter_id=P1, target_id=P3, reason="ещё")
    take = lambda who: client.post(f"{api}/reports/{rid2}", headers=h[who], json={"action": "take"})
    assert (await take(HELPER)).status_code == 200
    assert (await take(SENIOR)).status_code == 409
    mine = (await client.get(f"{api}/reports", headers=h[HELPER])).json()["items"]
    assert [x["handled_by"]["id"] for x in mine if x["id"] == rid2] == [HELPER], mine

    # ── Рассылки ────────────────────────────────────────────────────────────────
    # Удалившие аккаунт не получают общую рассылку.
    async with get_pool().acquire() as conn:
        everyone = await broadcasts.recipients(PGAdapter(conn), {"kind": "players"})
    assert GONE not in everyone and P1 in everyone, everyone
    # Админ-чаты отделяются от основных: фильтр «какие чаты» смотрит в chat_links.
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        await db.execute("INSERT INTO chat_settings (chat_id, chat_title) VALUES (-200, 'Админ-чат') "
                         "ON CONFLICT DO NOTHING")
        await db.execute("INSERT INTO chat_links (main_chat_id, admin_chat_id) VALUES (-100, -200) "
                         "ON CONFLICT DO NOTHING")
        main_chats = await broadcasts.recipients(db, {"kind": "chats", "chat_kind": "main"})
        admin_chats = await broadcasts.recipients(db, {"kind": "chats", "chat_kind": "admin"})
        every_chat = await broadcasts.recipients(db, {"kind": "chats"})
    assert main_chats == [-100] and admin_chats == [-200], (main_chats, admin_chats)
    assert set(every_chat) == {-100, -200}, every_chat
    # Кривой тип чатов — 400, а не 500.
    r = await client.post(f"{api}/broadcasts/preview", headers=h[CODER],
                          json={"segment": {"kind": "chats", "chat_kind": "нет"}})
    assert r.status_code == 400, (r.status_code, r.text)
    # Отказ по проверке не оставляет админу пробное сообщение.
    bot.sent.clear()
    r = await client.post(f"{api}/broadcasts", headers=h[CODER], json={"audience": "players", "text": "x" * 4000, "html": True})
    assert r.status_code == 400 and not bot.sent, (r.text, bot.sent)
    r = await client.post(f"{api}/broadcasts", headers=h[CODER], json={
        "audience": "players", "text": "<b>x</b>", "html": True, "segment": {"kind": "players", "players": [GONE]}})
    assert r.status_code == 400 and "Некому" in r.json()["detail"] and not bot.sent, (r.text, bot.sent)
    # Кривой формат — 400, а не 500.
    for body in ({"audience": "players", "text": "x", "segment": "x"}, {"audience": "players", "text": "x", "button": "x"},
                 {"audience": "players", "text": "x", "segment": {"kind": "players", "retry_of": "abc", "target_ids": [P1]}},
                 {"audience": "players", "text": "x", "segment": {"kind": "players", "players": [10 ** 30]}}):
        r = await client.post(f"{api}/broadcasts", headers=h[CODER], json=body)
        assert r.status_code == 400, (body, r.status_code, r.text)

    # «Остановить» сразу прерывает отправку, а «Продолжить» не запускает вторую параллельно.
    async with get_pool().acquire() as conn:
        for uid in range(7001, 7013):
            await PGAdapter(conn).execute("INSERT INTO users (user_tg_id, user_tg_username) VALUES (?, ?)", (uid, f"b{uid}"))
        made = await broadcasts.create(PGAdapter(conn), CODER, "players", "Длинная", "slow1", False,
                                       segment={"kind": "players", "players": list(range(7001, 7013))})
    bot.sent.clear()
    bot.delay = 0.05
    pool = broadcasts.pool_db_factory()
    task = broadcasts.start(bot, pool, made.id, "players", "Длинная", False, None)
    assert broadcasts.start(bot, pool, made.id, "players", "Длинная", False, None) is task   # второй запуск — та же задача
    await asyncio.sleep(0.2)
    assert (await client.post(f"{api}/broadcasts/{made.id}/stop", headers=h[CODER])).status_code == 200
    await asyncio.sleep(0.3)
    stopped_at = len(bot.sent)
    assert stopped_at < 12, stopped_at                      # пачку из двадцати не доделывает: стоп виден сразу
    r = await client.post(f"{api}/broadcasts/{made.id}/resume", headers=h[CODER])
    assert r.status_code == 200, r.text
    for _ in range(100):
        live = broadcasts._tasks.get(made.id)
        if live is None or live.done():
            break
        await asyncio.sleep(0.1)
    ids = [c for c, _ in bot.sent]
    assert sorted(ids) == list(range(7001, 7013)) and len(ids) == len(set(ids)), ids        # каждому ровно по разу
    bot.delay = 0.0

    # ── Кривые данные в запросах: понятный 400/404, а не 500 ─────────────────────
    assert (await client.get(f"{api}/search?q=²", headers=h[HELPER])).status_code == 200
    assert (await client.get(f"{api}/search?q=--5", headers=h[HELPER])).status_code == 200
    assert (await client.get(f"{api}/player/99999999999999999999", headers=h[HELPER])).status_code in (400, 404)
    act = lambda **b: client.post(f"{api}/player/{P2}/action", headers=h[CODER], json=b)
    assert (await act(action="balance", currency="mora", amount="1e30", reason="x")).status_code == 400
    assert (await act(action="mute", chat_id="abc", minutes=5, reason="x")).status_code == 400
    sw = lambda **b: client.post(f"{api}/switches", headers=h[DEV], json=b)
    assert (await sw(feature="all", chat_id=-777777, enabled=False)).status_code == 404
    promo = lambda **b: client.post(f"{api}/promo", headers=h[CODER], json=b)
    good = {"code": "TESTCODE", "rewards": [{"type": "mora", "amount": 10}]}
    assert (await promo(**{**good, "rewards": ["x"]})).status_code == 400
    assert (await promo(**{**good, "max_activations": 10 ** 12})).status_code == 400
    assert (await promo(**{**good, "allowed_chats": [10 ** 30]})).status_code == 400
    assert (await client.get(f"{api}/promo/TESTCODE", headers=h[CODER])).status_code == 404     # битый код не сохранился
    assert (await promo(**good)).status_code == 200
    assert (await promo(code="NEWAYEAR", rewards=good["rewards"])).status_code == 200
    found = (await client.get(f"{api}/promo?q=NEW_YEAR", headers=h[CODER])).json()["items"]
    assert found == [], found                                # «_» ищется как обычный символ, а не «любая буква»


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run())
    print("OK: bot admin review fixes on PostgreSQL")


main()
