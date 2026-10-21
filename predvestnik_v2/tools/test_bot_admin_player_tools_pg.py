"""Админка, игроки: быстрые фильтры поиска, «на контроле», история ников, связанные аккаунты, массовые действия.

Запуск: python tools/test_bot_admin_player_tools_pg.py --dsn postgresql://... (пустая тестовая БД!)
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

DEV, HELPER, SENIOR, CODER = 1001, 3003, 4004, 5005
P1, P2, P3, P4, P5 = 2001, 2002, 2003, 2004, 2005


async def prepare():
    from infrastructure.database import create_pool, get_pool
    from infrastructure.pg_adapter import PGAdapter
    from bot.core.database import init_db
    from bot.chat.schema import ensure_chat_schema
    from bot.chat.tracking import local_now
    from bot.startup_schema import ensure_runtime_schema
    from services import vip as vip_service
    await create_pool()
    await init_db()
    await ensure_runtime_schema(get_pool())
    await ensure_chat_schema()
    today = local_now().date().isoformat()
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        for uid, rank in ((DEV, 0), (HELPER, 3), (SENIOR, 4), (CODER, 5), (P1, 0), (P2, 0), (P3, 0), (P4, 0), (P5, 0)):
            await db.execute("INSERT INTO users (user_tg_id, user_tg_username, bot_rank) VALUES (?, ?, ?) "
                             "ON CONFLICT DO NOTHING", (uid, f"u{uid}", rank))
        for chat, title in ((-100, "Основной чат"), (-200, "Другой чат")):
            await db.execute("INSERT INTO chat_settings (chat_id, chat_title) VALUES (?, ?) ON CONFLICT DO NOTHING", (chat, title))
        # P1 — давний игрок, P4 — пришёл вчера, у P2/P3/P5 следов в чатах нет (новыми не считаются)
        await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, user_messages_count_all_time, is_left, "
                         "joined_at, membership_since, last_message_at) VALUES (?, -100, 50, FALSE, NOW() - INTERVAL '30 days', "
                         "NOW() - INTERVAL '30 days', NOW())", (P1,))
        await db.execute("INSERT INTO daily_user_stats (user_id, chat_id, date, message_count) VALUES (?, -100, ?, 5)",
                         (P1, (local_now().date().replace(day=1)).isoformat()))
        await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, user_messages_count_all_time, is_left, "
                         "joined_at, membership_since, last_message_at) VALUES (?, -100, 3, FALSE, NOW() - INTERVAL '1 day', "
                         "NOW() - INTERVAL '1 day', NOW())", (P4,))
        await db.execute("INSERT INTO daily_user_stats (user_id, chat_id, date, message_count) VALUES (?, -100, ?, 3)", (P4, today))
        await vip_service.grant_vip_days(db, P1, "vip", 5)
        await db.execute("INSERT INTO chat_blacklist (chat_id, user_id, reason, added_by) VALUES (-100, ?, 'спам', ?)", (P2, SENIOR))
        await db.execute("INSERT INTO user_warnings (chat_id, user_id, admin_id, reason) VALUES (-100, ?, ?, 'флуд')", (P3, SENIOR))
        await db.execute("INSERT INTO user_warnings (chat_id, user_id, admin_id, reason) VALUES (-200, ?, ?, 'ещё флуд')", (P3, SENIOR))
        await db.execute("INSERT INTO user_warnings (chat_id, user_id, admin_id, reason, expires_at) "
                         "VALUES (-100, ?, ?, 'старый', NOW() - INTERVAL '1 day')", (P5, SENIOR))   # сгоревший варн не считается


class Client:
    def __init__(self, app):
        import httpx
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    def __getattr__(self, method):
        return getattr(self.http, method)


async def checks():
    from FastAPI.auth import create_session_token
    import FastAPI.main as main
    from infrastructure.database import get_pool
    from infrastructure.pg_adapter import PGAdapter
    from bot.chat.tracking import record_message

    client = Client(main.app)
    h = {uid: {"x-session-token": create_session_token(uid)} for uid in (DEV, HELPER, SENIOR, CODER, P1)}

    async def find(who, **q):
        r = await client.get("/bot-admin/api/search", headers=h[who], params=q)
        assert r.status_code == 200, r.text
        return r.json()

    ids = lambda found: sorted(p["id"] for p in found["players"])

    # ── Быстрые фильтры ──
    assert ids(await find(HELPER, filter="vip")) == [P1]
    assert ids(await find(HELPER, filter="banned")) == [P2]
    assert ids(await find(HELPER, filter="warned")) == [P3]                          # сгоревший варн P5 не считается
    assert ids(await find(HELPER, filter="new")) == [P4]                            # P1 давний, у остальных нет следов в чатах
    assert ids(await find(HELPER, filter="staff")) == sorted([HELPER, SENIOR, CODER])
    f = await find(HELPER, filter="vip")
    assert f["chats"] == [] and f["total"] == 1, f
    assert ids(await find(HELPER, q="u2001", filter="vip")) == [P1] and ids(await find(HELPER, q="u2002", filter="vip")) == []
    assert ids(await find(HELPER, q="2002", filter="banned")) == [P2] and ids(await find(HELPER, q="2001", filter="banned")) == []
    assert ids(await find(HELPER, q="@u200", filter="warned")) == [P3]
    assert (await find(HELPER, q="основ", filter="vip"))["chats"] == [], "с фильтром ищем только игроков"
    plain = await find(HELPER, filter="nope")                                       # неизвестный фильтр = без фильтра
    assert plain["chats"] and "total" not in plain, plain
    assert ids(await find(HELPER, filter="watch")) == []

    # ── На контроле ──
    watch = lambda who, uid, **b: client.post(f"/bot-admin/api/player/{uid}/watch", headers=h[who], json=b)
    assert (await watch(P1, P2, on=True)).status_code == 403
    assert (await watch(HELPER, 9999, on=True)).status_code == 404
    r = await watch(HELPER, P2, on=True, reason="спорит с модераторами")
    assert r.status_code == 200 and r.json()["watch"]["reason"] == "спорит с модераторами" and r.json()["watch"]["by"]["id"] == HELPER, r.text
    r = await watch(SENIOR, P2, on=True, reason="другая причина")                   # повтор не перезаписывает автора и причину
    assert r.json()["watch"]["by"]["id"] == HELPER and r.json()["watch"]["reason"] == "спорит с модераторами", r.text
    card = (await client.get(f"/bot-admin/api/player/{P2}", headers=h[SENIOR])).json()
    assert card["watch"]["reason"] == "спорит с модераторами", card["watch"]
    assert {"Игрок поставлен на контроль"} <= {x["title"] for x in card["history"]}
    assert sum(x["action"] == "watch_add" for x in card["history"]) == 1, "повтор не пишется в журнал дважды"
    assert ids(await find(HELPER, filter="watch")) == [P2]
    r = await watch(SENIOR, P2, on=False)
    assert r.status_code == 200 and r.json()["watch"] is None, r.text
    assert ids(await find(HELPER, filter="watch")) == []
    assert (await watch(HELPER, P2, on=False)).status_code == 200                   # снять ещё раз — не ошибка
    r = await watch(HELPER, P2, on=True, reason="снова")                            # поставить после снятия можно
    assert r.json()["watch"]["reason"] == "снова", r.text
    feed = (await client.get("/bot-admin/api/journal?kind=players&days=1", headers=h[DEV])).json()
    assert {"Игрок поставлен на контроль", "Игрок снят с контроля"} <= {x["title"] for x in feed["items"]}, feed
    async with get_pool().acquire() as conn:
        async with PGAdapter(conn).execute("SELECT COUNT(*) FROM bot_staff_watch WHERE user_id = ?", (P2,)) as cur:
            assert (await cur.fetchone())[0] == 1                                    # снятие ничего не стирает, строка одна

    # ── История ников и связанные аккаунты ──
    def msg(uid, username, full_name, chat=-100):
        return SimpleNamespace(from_user=SimpleNamespace(id=uid, is_bot=False, username=username, full_name=full_name),
                               chat=SimpleNamespace(id=chat, type="supergroup", title="Основной чат"))

    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        await record_message(db, msg(P1, "shared", "Общее Имя Тест"))
        await record_message(db, msg(P1, "shared", "Общее Имя Тест"))                # без изменений — новой записи нет
        await record_message(db, msg(P1, "p1new", "Общее Имя Тест"))
        await record_message(db, msg(P3, "shared", "Другой Человек"))                # занял освободившийся ник
        await record_message(db, msg(P4, "fresh4", "Общее Имя Тест"))
        await db.execute("UPDATE users SET referred_by = ? WHERE user_tg_id IN (?, ?)", (P1, P3, P4))
    card = (await client.get(f"/bot-admin/api/player/{P1}", headers=h[HELPER])).json()
    assert sorted((n["kind"], n["value"]) for n in card["names"]) == sorted(
        [("username", "p1new"), ("username", "shared"), ("name", "Общее Имя Тест")]), card["names"]
    assert card["names"][0]["value"] == "p1new" and card["names"][0]["at"], card["names"]   # свежее первым
    assert "nicknames" not in card, "ники старого бота удалены"
    assert card["linked"] is None, "младшие хелперы связей не видят"
    assert (await client.get(f"/bot-admin/api/player/{P1}", headers=h[HELPER])).json()["linked"] is None
    link = (await client.get(f"/bot-admin/api/player/{P1}", headers=h[SENIOR])).json()["linked"]
    assert [x["id"] for x in link["same_username"]] == [P3] and link["same_username"][0]["value"] == "shared", link
    assert [x["id"] for x in link["same_name"]] == [P4], link                        # совпавшее имя; P3 с другим именем не в списке
    assert link["invited_by"] is None and link["invited"]["total"] == 2 and {x["id"] for x in link["invited"]["items"]} == {P3, P4}, link
    link3 = (await client.get(f"/bot-admin/api/player/{P3}", headers=h[CODER])).json()["linked"]
    assert link3["invited_by"]["id"] == P1 and [x["id"] for x in link3["same_username"]] == [P1], link3
    short = (await client.get(f"/bot-admin/api/player/{P5}", headers=h[SENIOR])).json()["linked"]
    assert short == {"same_username": [], "same_name": [], "invited_by": None, "invited": {"total": 0, "items": []}}, short
    async with get_pool().acquire() as conn:
        async with PGAdapter(conn).execute("SELECT COUNT(*) FROM user_name_history WHERE user_id = ?", (P1,)) as cur:
            assert (await cur.fetchone())[0] == 3, "повторное сообщение с тем же ником историю не растит"

    # ── Массовые действия ──
    bulk = lambda who, **b: client.post("/bot-admin/api/players/bulk", headers=h[who], json=b)
    assert (await bulk(P1, action="watch", ids=[P2])).status_code == 403
    assert (await bulk(HELPER, action="nope", ids=[P2])).status_code == 400
    assert (await bulk(HELPER, action="watch", ids=[])).status_code == 400
    assert (await bulk(HELPER, action="watch", ids="abc")).status_code == 400
    assert (await bulk(HELPER, action="watch", ids=["x"])).status_code == 400
    assert (await bulk(HELPER, action="watch", ids=list(range(1, 52)))).status_code == 400
    r = await bulk(HELPER, action="watch", ids=[P1, P3, 99999, P1], reason="в списке конкурса")
    out = r.json()
    assert r.status_code == 200 and out["done"] == 2 and out["failed"] == [{"id": 99999, "username": None, "reason": "Игрок не найден."}], out
    assert out["message"] == "Готово: 2 из 3.", out                                   # дубль в списке схлопнут
    assert ids(await find(HELPER, filter="watch")) == sorted([P1, P2, P3])
    r = await bulk(HELPER, action="unwatch", ids=[P1, P3])
    assert r.json()["done"] == 2 and ids(await find(HELPER, filter="watch")) == [P2]

    r = await bulk(HELPER, action="unwarn_all", ids=[P3, P5, SENIOR])                # у P3 варны в двух чатах, у P5 нет действующих
    out = r.json()
    assert out["done"] == 2 and out["message"] == "Готово: 2 из 3. Снято варнов: 2." and [x["id"] for x in out["failed"]] == [SENIOR], out
    assert "не ниже вашей" in out["failed"][0]["reason"], out
    assert ids(await find(HELPER, filter="warned")) == []

    assert (await bulk(HELPER, action="mark_grant", ids=[P1], mark="founder", reason="x")).status_code == 403   # метки — с разработчика
    assert "причину" in (await bulk(CODER, action="mark_grant", ids=[P1], mark="founder")).json()["detail"]
    r = await bulk(CODER, action="mark_grant", ids=[P1, P2, DEV, CODER], mark="founder", reason="с первых дней")
    out = r.json()
    assert out["done"] == 2 and {x["id"] for x in out["failed"]} == {DEV, CODER}, out
    assert "неприкосновенен" in next(x for x in out["failed"] if x["id"] == DEV)["reason"], out
    again = (await bulk(CODER, action="mark_grant", ids=[P1, P4], mark="founder", reason="с первых дней")).json()
    assert again["done"] == 1 and again["failed"][0]["id"] == P1 and "уже есть" in again["failed"][0]["reason"], again
    bad = (await bulk(CODER, action="mark_grant", ids=[P4], mark="streak30", reason="x")).json()
    assert bad["done"] == 0 and "сам" in bad["failed"][0]["reason"], bad
    card = (await client.get(f"/bot-admin/api/player/{P1}", headers=h[CODER])).json()
    assert [m["id"] for m in card["marks"]["given"]] == ["founder"] and any(x["action"] == "mark_grant" for x in card["history"]), card["marks"]
    out = (await bulk(CODER, action="mark_revoke", ids=[P1, P2, P3], mark="founder", reason="ошибка")).json()
    assert out["done"] == 2 and out["failed"][0]["id"] == P3 and "нет такой метки" in out["failed"][0]["reason"], out


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(prepare())
    loop.run_until_complete(checks())
    print("OK: bot admin player tools on PostgreSQL")


main()
