"""Админка S10, серверная часть: поиск со страницами и фильтрами, статус в строке, кошелёк и образы в карточке,
образы только у создателя (промокоды тоже), журнал с «Чисткой», фильтром по игроку и выгрузкой, массовое снятие мута,
живой значок жалоб, защита и иммунитет одной логикой для бота и админки.

Запуск: python tools/test_bot_admin_s10_pg.py --dsn postgresql://... (пустая тестовая БД!)
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

DEV, HELPER, CODER, P1, P2, P3, IDLE, SILENT = 1001, 3003, 5005, 2002, 2003, 2004, 2005, 2006


class FakeBot:
    def __init__(self):
        self.calls = []

    async def restrict_chat_member(self, chat_id, user_id, permissions=None, until_date=None):
        self.calls.append(("restrict", chat_id, user_id))
        if chat_id == -200:
            raise RuntimeError("Bad Request: not enough rights to restrict/unrestrict chat member")

    async def get_chat(self, chat_id):
        return SimpleNamespace(permissions=None)

    async def send_message(self, chat_id, text, **kw):
        self.calls.append(("send", chat_id, text))


class Client:
    def __init__(self, app):
        import httpx
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    def __getattr__(self, method):
        return getattr(self.http, method)


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
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        for uid, rank, name in ((DEV, 0, "Создатель"), (HELPER, 3, "Хелпер"), (CODER, 5, "Кодер"), (P1, 0, "Анна Первая"),
                                (P2, 0, "Борис"), (P3, 0, "Анна Вторая"), (IDLE, 0, "Давний"), (SILENT, 0, "Молчун")):
            await db.execute("INSERT INTO users (user_tg_id, user_tg_username, bot_rank, user_tg_name) VALUES (?, ?, ?, ?) "
                             "ON CONFLICT DO NOTHING", (uid, f"u{uid}", rank, name))
        await db.execute("UPDATE users SET referred_by = ? WHERE user_tg_id = ?", (P1, P3))   # P3 пришёл по приглашению P1
        for chat, title in ((-100, "Основной чат"), (-200, "Чат без прав")):
            await db.execute("INSERT INTO chat_settings (chat_id, chat_title) VALUES (?, ?) ON CONFLICT DO NOTHING", (chat, title))
        for uid, chat, n, ago in ((P1, -100, 50, 0), (P2, -100, 10, 2), (P3, -100, 5, 3), (IDLE, -100, 3, 40), (P1, -200, 1, 0)):
            await db.execute(
                "INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, user_messages_count_all_time, is_left, last_message_at) "
                "VALUES (?, ?, ?, FALSE, NOW() - make_interval(days => ?))", (uid, chat, n, ago))
        await db.execute("INSERT INTO user_warnings (chat_id, user_id, admin_id, reason) VALUES (-100, ?, ?, 'флуд')", (P2, HELPER))
        await db.execute("INSERT INTO chat_blacklist (chat_id, user_id, reason) VALUES (-100, ?, 'спам')", (P3,))
        await db.execute("UPDATE user_chat_stats SET muted_until = NOW() + INTERVAL '1 hour' WHERE user_tg_id = ? AND chat_tg_id IN (-100, -200)", (P1,))
        await db.execute("INSERT INTO moderation_logs (chat_id, user_id, admin_id, action, reason) VALUES (-100, 0, ?, 'purge_start', 'норма 10')", (HELPER,))
        await db.execute("INSERT INTO moderation_logs (chat_id, user_id, admin_id, action, reason) VALUES (-100, ?, ?, 'warn', '=HYPERLINK(1)')", (P1, HELPER))


async def checks():
    from FastAPI.auth import create_session_token
    import FastAPI.main as main
    from FastAPI import notifications
    from FastAPI.routers.bot_admin import people
    from infrastructure.database import get_pool
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import skins_v3 as skins_repo
    from core.skins_v3_catalog import SKINS
    from services import skins_v3 as skins, reports as reports_service
    from bot.chat import moderation

    bot = FakeBot()
    people.set_bot(bot)
    client = Client(main.app)
    h = {uid: {"x-session-token": create_session_token(uid)} for uid in (DEV, HELPER, CODER, P1)}

    async def get(who, path):
        r = await client.get(f"/bot-admin/api{path}", headers=h[who])
        assert r.status_code == 200, (path, r.status_code, r.text)
        return r.json()

    # ── Поиск: без paged ответ прежний (старый экран), с paged — страницы, фильтры, статус ──
    old = await get(HELPER, "/search?q=анна")
    assert sorted(p["id"] for p in old["players"]) == [P1, P3] and "offset" not in old and old["chats"] == [], old
    assert {p["id"]: p["status"] for p in old["players"]}[P3] == {"ban": True, "global_ban": False, "mute": False, "warns": 0}, old
    assert {p["id"]: p["status"] for p in old["players"]}[P1]["mute"], old
    old_flt = await get(HELPER, "/search?filter=warned")
    assert [p["id"] for p in old_flt["players"]] == [P2] and "offset" not in old_flt and old_flt["players"][0]["status"]["warns"] == 1, old_flt

    page = await get(HELPER, "/search?q=анна&paged=1")
    assert page["total"] == 2 and page["offset"] == 0 and page["next_offset"] is None and page["limit"] == 20, page
    idle = await get(HELPER, "/search?filter=idle:30&paged=1")
    assert [p["id"] for p in idle["players"]] == [IDLE] and idle["filter_title"] == "Не писали 30+ дн.", idle
    active = await get(HELPER, "/search?filter=active:7&paged=1")
    assert sorted(p["id"] for p in active["players"]) == [P1, P2, P3], active
    active1 = await get(HELPER, "/search?filter=active:1&paged=1")
    assert [p["id"] for p in active1["players"]] == [P1], active1
    silent = await get(HELPER, "/search?filter=silent&paged=1")
    assert {DEV, HELPER, CODER, SILENT} <= {p["id"] for p in silent["players"]} and P1 not in {p["id"] for p in silent["players"]}, silent
    linked = await get(CODER, f"/search?filter=linked:{P1}&paged=1")
    assert [p["id"] for p in linked["players"]] == [P3] and linked["filter_title"] == f"Связи игрока id{P1}", linked
    hidden = await get(HELPER, f"/search?filter=linked:{P1}&paged=1")   # связи видят со старшего хелпера, как в карточке
    assert "filter_title" not in hidden and len(hidden["players"]) > 1, hidden
    unpaged = await get(HELPER, "/search?filter=idle:30")   # старый экран фильтр с числом не знает: и подписи нет
    assert "filter_title" not in unpaged, unpaged
    both = await get(HELPER, "/search?q=анна&filter=active:1&paged=1")
    assert [p["id"] for p in both["players"]] == [P1] and both["chats"] == [], both
    for bad in ("idle:0", "idle:9999", "active:x", "linked:", "nope"):
        r = await get(HELPER, f"/search?filter={bad}&paged=1")   # чужой фильтр — как без фильтра, не 500
        assert "players" in r, (bad, r)
    by_id = await get(HELPER, f"/search?q={P2}&paged=1")
    assert [p["id"] for p in by_id["players"]] == [P2] and by_id["total"] == 1, by_id
    chats = await get(HELPER, "/search?q=основ&paged=1")
    assert [c["id"] for c in chats["chats"]] == [-100], chats
    # Страницы: 30 на фильтр, дальше — next_offset
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        for i in range(35):
            await db.execute("INSERT INTO users (user_tg_id, user_tg_username) VALUES (?, ?) ON CONFLICT DO NOTHING", (900_000 + i, f"bulk{i}"))
    first = await get(HELPER, "/search?filter=silent&paged=1")
    assert len(first["players"]) == 30 and first["next_offset"] == 30 and first["total"] >= 39, first
    second = await get(HELPER, f"/search?filter=silent&paged=1&offset={first['next_offset']}")
    assert second["players"] and not {p["id"] for p in second["players"]} & {p["id"] for p in first["players"]}, second
    text = await get(HELPER, "/search?q=bulk&paged=1")
    assert len(text["players"]) == 20 and text["total"] == 35 and text["next_offset"] == 20, text
    assert all("avatar" in p for p in text["players"]), "фото у любого игрока, не только VIP"

    # ── Карточка: кошелёк и образы (видят все, кто открывает карточку) ──
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        await skins_repo.ensure_tables(db)
        await skins_repo.essence_apply(db, P1, 30, reason="quest", reference="q1", idempotency_key="t1")
    r = await client.post(f"/bot-admin/api/player/{P1}/action", headers=h[CODER],
                          json={"action": "balance", "currency": "mora", "amount": "250", "reason": "приз"})
    assert r.status_code == 200, r.text
    card = await get(HELPER, f"/player/{P1}")
    assert [(w["code"], w["delta"]) for w in card["wallet"][:2]] == [("mora", "250"), ("essence", "30")], card["wallet"]
    assert card["wallet"][0]["reason"] == "Выдано и списано из админки" and card["wallet"][0]["after"] == "250", card["wallet"]
    assert card["skins"] == {"equipped": None, "items": []}, card["skins"]
    assert "skin_revoke" in card["confirm_rules"]["actions"], card["confirm_rules"]

    # ── Образы: выдаёт и забирает только создатель ──
    assert (await client.get("/bot-admin/api/skins/catalog", headers=h[CODER])).status_code == 403
    catalog = await get(DEV, "/skins/catalog")
    plain = catalog["skins"][0]["id"]
    private = catalog["private_skins"][0]["id"]
    assert sorted([x["id"] for x in catalog["skins"]] + [x["id"] for x in catalog["private_skins"]]) == sorted(SKINS)
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        assert await skins.grant_by_hand(db, P1, plain, "приз за ивент") == SKINS[plain]["name"]
        for coro, text_ in ((skins.grant_by_hand(db, P1, plain, "ещё"), "уже у игрока"), (skins.grant_by_hand(db, P1, plain, " "), "причину"),
                            (skins.grant_by_hand(db, P1, "nope", "x"), "Такого образа нет"), (skins.grant_by_hand(db, 777, plain, "x"), "Такого игрока нет")):
            try:
                await coro
                raise AssertionError(text_)
            except skins.SkinConflict as exc:
                assert text_ in str(exc), (text_, exc)
        assert await skins.grant_by_hand(db, P1, private, "вклад") == SKINS[private]["name"]
        try:
            await skins.grant_by_hand(db, P2, private, "второму")
            raise AssertionError("личный образ ушёл второму")
        except skins.SkinConflict as exc:
            assert "для одного игрока" in str(exc), exc
        await skins.equip(db, P1, plain)
        inv = await skins.inventory(db, P1)
        assert inv["equipped"] == plain and {i["id"] for i in inv["items"]} == {plain, private}, inv
        assert next(i for i in inv["items"] if i["id"] == private)["exclusive"], inv
        assert await skins.revoke_by_hand(db, P1, plain, "ошибка") == SKINS[plain]["name"]
        assert await skins_repo.equipped(db, P1) is None, "снятый образ не остаётся надетым"
        assert await skins.revoke_by_hand(db, P1, private, "ошибка") == SKINS[private]["name"]
        try:
            await skins.revoke_by_hand(db, P1, plain, "ещё")
            raise AssertionError("забрали то, чего нет")
        except skins.SkinConflict as exc:
            assert "нет этого образа" in str(exc), exc

    # ── Промокод с образом: только создатель (создать, изменить, пачка) ──
    skin_reward = {"type": "skin", "id": plain}
    opts = await get(CODER, "/promo-options")
    assert "skin" not in [x["type"] for x in opts["rewards"]], opts["rewards"]
    assert "skin" in [x["type"] for x in (await get(DEV, "/promo-options"))["rewards"]]
    r = await client.post("/bot-admin/api/promo", headers=h[CODER], json={"code": "SKIN-X", "max_activations": 1, "rewards": [skin_reward]})
    assert r.status_code == 400 and "только создатель" in r.json()["detail"], r.text
    r = await client.post("/bot-admin/api/promo/bulk", headers=h[CODER], json={"prefix": "skx", "count": 2, "rewards": [skin_reward]})
    assert r.status_code == 400 and "только создатель" in r.json()["detail"], r.text
    r = await client.post("/bot-admin/api/promo", headers=h[CODER], json={"code": "MORA-X", "max_activations": 1, "rewards": [{"type": "mora", "amount": 5}]})
    assert r.status_code == 200, r.text
    r = await client.put("/bot-admin/api/promo/MORA-X", headers=h[CODER], json={"max_activations": 1, "rewards": [skin_reward]})
    assert r.status_code == 400 and "только создатель" in r.json()["detail"], r.text   # обход через правку своего кода
    r = await client.post("/bot-admin/api/promo", headers=h[DEV], json={"code": "SKIN-OK", "max_activations": 1, "rewards": [skin_reward]})
    assert r.status_code == 200, r.text
    assert (await client.post("/bot-admin/api/promo/SKIN-OK/active", headers=h[DEV], json={"active": False})).status_code == 200
    r = await client.post("/bot-admin/api/promo/SKIN-OK/active", headers=h[CODER], json={"active": True})   # включить = выдать
    assert r.status_code == 400 and "только создатель" in r.json()["detail"], r.text
    assert (await client.post("/bot-admin/api/promo/SKIN-OK/active", headers=h[CODER], json={"active": False})).status_code == 200
    assert (await client.post("/bot-admin/api/promo/MORA-X/active", headers=h[CODER], json={"active": True})).status_code == 200

    # ── Журнал: «Чистка» в ленте, фильтр по игроку и чату, выгрузка ──
    feed = await get(CODER, "/journal?kind=purge")
    assert [x["action"] for x in feed["items"]] == ["purge_start"] and "purge" in [k["key"] for k in feed["kinds"]], feed
    mine = await get(CODER, f"/journal?user_id={P1}&days=1")
    assert mine["items"] and all(x["user"]["id"] == P1 for x in mine["items"]), mine
    in_chat = await get(CODER, "/journal?chat_id=-100")
    assert in_chat["items"] and all(x["chat"]["id"] == -100 for x in in_chat["items"]), in_chat
    r = await client.get(f"/bot-admin/api/journal/export?days=500&user_id={P1}", headers=h[CODER])
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv"), r.text
    assert r.text.startswith("﻿Когда (UTC);Действие") and "Баланс" in r.text and "журнал" not in r.text.lower().split("\n")[1], r.text[:300]
    assert "'=HYPERLINK(1)" in r.text and ";=HYPERLINK" not in r.text, "текст из чата не становится формулой"
    assert (await client.get("/bot-admin/api/journal/export", headers=h[HELPER])).status_code == 403   # журнал — с роли 4
    latest = (await get(CODER, "/journal?kind=settings"))["items"][0]
    assert latest["action"] == "journal_export" and latest["text"].startswith("за 90 дней"), latest

    # ── Массово: снять мут везде; Telegram отказал в одном чате — игрок в «не вышло» с причиной ──
    r = await client.post("/bot-admin/api/players/bulk", headers=h[HELPER], json={"action": "unmute_all", "ids": [P1, P2]})
    body = r.json()
    assert r.status_code == 200 and body["done"] == 1 and body["failed"][0]["id"] == P1, body
    assert "прав администратора" in body["failed"][0]["reason"], body
    assert ("restrict", -100, P1) in bot.calls, bot.calls
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        await db.execute("UPDATE user_chat_stats SET muted_until = NULL WHERE user_tg_id = ? AND chat_tg_id = -200", (P1,))
        await db.execute("UPDATE user_chat_stats SET muted_until = NOW() + INTERVAL '1 hour' WHERE user_tg_id = ? AND chat_tg_id = -100", (P2,))
    body = (await client.post("/bot-admin/api/players/bulk", headers=h[HELPER], json={"action": "unmute_all", "ids": [P2, CODER]})).json()
    assert body["done"] == 1 and body["message"] == "Готово: 1 из 2. Снято мутов: 1." and body["failed"][0]["id"] == CODER, body   # роль выше
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        await db.execute("UPDATE user_chat_stats SET muted_until = NOW() + INTERVAL '1 hour' WHERE user_tg_id = ? AND chat_tg_id IN (-100, -200)", (P1,))
    body = (await client.post("/bot-admin/api/players/bulk", headers=h[HELPER], json={"action": "unmute_all", "ids": [P1]})).json()
    assert body["done"] == 0 and "Не везде" in body["failed"][0]["reason"] and "Чат без прав" in body["failed"][0]["reason"], body
    async with get_pool().acquire() as conn:   # отказ в одном чате не остановил другой
        assert await conn.fetchval("SELECT muted_until IS NULL FROM user_chat_stats WHERE user_tg_id = $1 AND chat_tg_id = -100", P1)
    assert (await client.post("/bot-admin/api/players/bulk", headers=h[P1], json={"action": "unmute_all", "ids": [P2]})).status_code == 403

    # ── Живой значок жалоб: персонал онлайн получает сигнал, игрок — нет ──
    staff_q, player_q = asyncio.Queue(), asyncio.Queue()
    notifications.register(HELPER, staff_q)
    notifications.register(P2, player_q)
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        await reports_service.ensure_schema(db)
        assert set(await reports_service.staff_watchers(db)) == {DEV, HELPER, CODER}
        rid = await reports_service.create(db, chat_id=-100, reporter_id=P2, target_id=P1, reason="спам")
    r = await client.post(f"/bot-admin/api/reports/{rid}", headers=h[HELPER], json={"action": "take"})
    assert r.status_code == 200, r.text
    assert staff_q.get_nowait() == {"type": "data_changed", "scope": "admin_reports"} and player_q.empty()
    from bot.chat.reports import _live_badge
    async with get_pool().acquire() as conn:
        await _live_badge(PGAdapter(conn))
    assert staff_q.get_nowait()["scope"] == "admin_reports"
    notifications.unregister(HELPER, staff_q)
    notifications.unregister(P2, player_q)

    # ── Защита и иммунитет: одна логика для команды бота и админки ──
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        await moderation.do_shield(db, -100, P2, HELPER, timedelta(days=2))
        await moderation.set_protection(db, -100, P2, HELPER, "immune")
        rows = await moderation.protected(db, -100)
        assert [(r[0], r[2], r[3] is not None) for r in rows] == [(P2, True, True)], rows
        await moderation.set_protection(db, -100, P2, HELPER, "unshield")
        await moderation.set_protection(db, -100, P2, HELPER, "unimmune")
        assert await moderation.protected(db, -100) == []
        async with db.execute("SELECT action FROM moderation_logs WHERE user_id = ? AND chat_id = -100 ORDER BY id", (P2,)) as cur:
            assert [r[0] for r in await cur.fetchall()][-4:] == ["shield", "immune", "unshield", "unimmune"]
    feed = await get(CODER, "/journal?kind=moderation")
    assert {"Защита", "Иммунитет"} <= {x["title"] for x in feed["items"]}, feed


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(prepare())
    loop.run_until_complete(checks())
    print("OK: S10 admin server — paged search and filters, row status, wallet and skins in the card, skins creator-only "
          "(card, promo create/update/bulk), journal purge/filters/export, bulk unmute, live report badge, shared shield/immune")


main()
