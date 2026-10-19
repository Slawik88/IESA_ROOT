"""Админка: настройки чата одним взглядом, чаты «требуют внимания», значок жалоб и повторные нарушители.

Запуск: python tools/test_bot_admin_chats_reports_pg.py --dsn postgresql://... (пустая тестовая БД!)
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

DEV, HELPER, SENIOR = 1001, 3003, 4004
P = {n: 2000 + n for n in range(1, 8)}      # игроки 2001..2007


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
    today = local_now().date().isoformat()
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        for uid, rank in ((DEV, 0), (HELPER, 3), (SENIOR, 4), *((u, 0) for u in P.values())):
            await db.execute("INSERT INTO users (user_tg_id, user_tg_username, bot_rank) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                             (uid, f"u{uid}", rank))
        # -100: бот без прав модерации, но пишут; -200: тихий; -300: бота удалили; -400: всё хорошо; -500: бот не админ, право не известно
        for cid, title, mod, admin, left in ((-100, "Без прав", False, True, False), (-200, "Тихий", True, True, False),
                                             (-300, "Удалили", True, True, True), (-400, "Здоровый", True, True, False),
                                             (-500, "Не админ", None, False, False)):
            await db.execute("INSERT INTO chat_settings (chat_id, chat_title, bot_can_moderate, bot_is_admin, bot_left_at) "
                             "VALUES (?, ?, ?, ?, CASE WHEN ? THEN NOW() ELSE NULL END)", (cid, title, mod, admin, left))
        for cid in (-100, -400, -500):
            await db.execute("INSERT INTO daily_user_stats (user_id, chat_id, date, message_count) VALUES (?, ?, ?, 4)", (P[1], cid, today))
        for cid, n in ((-100, 3), (-400, 9)):
            await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, user_messages_count_all_time, is_left, last_message_at) "
                             "VALUES (?, ?, ?, FALSE, NOW())", (P[1], cid, n))
        await db.execute("UPDATE chat_settings SET rank_ban = 6, is_purging = TRUE, purge_min_rank = 5, module_mafia = 0, "
                         "events_enabled = 0, shield_duration_days = 7 WHERE chat_id = -400")


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

    client = Client(main.app)
    h = {uid: {"x-session-token": create_session_token(uid)} for uid in (DEV, HELPER, SENIOR, P[1])}
    get = lambda who, path: client.get(f"/bot-admin/api{path}", headers=h[who])

    # ── Настройки чата ──
    card = (await get(HELPER, "/chat/-400")).json()
    st = card["settings"]
    ranks_ = {r["key"]: r for r in st["ranks"]}
    assert [r["title"] for r in st["ranks"]] == ["Варн", "Мут", "Кик", "Бан", "Защита", "Иммунитет"], st["ranks"]
    assert ranks_["rank_ban"]["rank"] == 6 and ranks_["rank_warn"]["rank"] == 2 and ranks_["rank_ban"]["name"], ranks_
    assert st["purge"]["on"] and st["purge"]["min_rank"] and st["shield_days"] == 7, st
    modules = {m["key"]: m["on"] for m in st["modules"]}
    assert modules["module_mafia"] is False and modules["module_pets"] is True and modules["module_echo"] is False, modules
    flags = {f["title"]: f["on"] for f in st["flags"]}
    assert flags["События чата"] is False and flags["Участие в общем топе"] is True, flags
    assert (await get(HELPER, "/chat/-100")).json()["settings"]["purge"]["on"] is False

    # ── Чаты, которым нужно внимание ──
    assert (await get(P[1], "/chats/attention")).status_code == 403
    att = (await get(HELPER, "/chats/attention")).json()
    got = {c["id"]: [p["key"] for p in c["problems"]] for c in att["items"]}
    assert got == {-100: ["no_rights"], -200: ["quiet"], -300: ["left"], -500: ["no_rights"]}, got       # -400 здоров
    assert att["total"] == 4 and att["items"][0]["id"] == -100 and att["items"][0]["members"] == 1, att     # больше участников — выше
    only = {c["id"] for c in (await get(HELPER, "/chats/attention?kind=no_rights")).json()["items"]}
    assert only == {-100, -500}, only
    assert {c["id"] for c in (await get(HELPER, "/chats/attention?kind=quiet")).json()["items"]} == {-200}
    assert (await get(HELPER, "/chats/attention?kind=nonsense")).json()["total"] == 4                       # неизвестный вид = все
    # ── Подключение чатов: воронка из мастера настройки ──
    assert (await get(P[1], "/chats/onboarding")).status_code == 403
    assert (await get(HELPER, "/chats/onboarding")).json()["added"] == 0
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        await db.execute("INSERT INTO chat_onboarding (chat_id, inviter_id, rights_ok_at) VALUES (-100, ?, NULL), (-400, ?, NOW())", (P[2], P[3]))
        await db.execute("INSERT INTO chat_onboarding (chat_id, inviter_id, left_at) VALUES (-300, ?, NOW())", (P[4],))
        for chat, event in ((-100, "added"), (-100, "rights_help"), (-100, "rights_help"), (-400, "added"), (-400, "rights_ok"), (-300, "added")):
            await db.execute("INSERT INTO chat_onboarding_events (chat_id, user_id, event) VALUES (?, ?, ?)", (chat, P[2], event))
    funnel = (await get(HELPER, "/chats/onboarding?days=7")).json()
    assert (funnel["added"], funnel["ready"], funnel["waiting"], funnel["gave_up"]) == (3, 1, 1, 1), funnel
    events_ = {e["event"]: e for e in funnel["events"]}
    assert events_["rights_help"]["count"] == 2 and events_["rights_help"]["chats"] == 1 and events_["added"]["chats"] == 3, events_
    assert [s["id"] for s in funnel["stuck"]] == [-100] and funnel["stuck"][0]["inviter"]["username"] == f"u{P[2]}", funnel["stuck"]
    assert (await get(HELPER, "/chats/onboarding?days=9999")).json()["days"] == 90
    health = (await get(SENIOR, "/health")).json()
    assert health["chats"]["no_rights"] == 2 and health["chats"]["left"] == 1, health["chats"]               # «Состояние» считает так же

    # ── Жалобы: значок и повторные нарушители ──
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        from services import reports as reports_service
        await reports_service.ensure_schema(db)

        async def report(target, reporter, status="new", days_ago=0):
            await db.execute("INSERT INTO bot_reports (chat_id, reporter_id, target_id, reason, status, created_at) "
                             "VALUES (-400, ?, ?, 'грубит', ?, NOW() - make_interval(days => ?))", (reporter, target, status, days_ago))

        for reporter in (P[2], P[3], P[4]):                    # на P5 — трое разных
            await report(P[5], reporter)
        await report(P[5], P[2], "rejected")                   # отклонённая не считается
        await report(P[5], P[6], "resolved", days_ago=40)      # старше 30 дней не считается
        for _ in range(3):                                     # на P6 — три от одного игрока
            await report(P[6], P[2])
        await report(P[7], P[2])
        await report(P[7], P[3])                               # на P7 только две
        await report(P[7], P[4], "rejected")
    badges = lambda who: client.get("/bot-admin/api/badges", headers=h[who])
    assert (await badges(P[1])).status_code == 403
    assert (await badges(HELPER)).json() == {"reports": 8}, (await badges(HELPER)).text      # новых: 3 + 3 + 2; отклонённые и закрытая старая не новые
    rep = (await get(HELPER, "/reports")).json()
    repeat = {r["id"]: r for r in rep["repeat"]}
    assert set(repeat) == {P[5], P[6]}, repeat
    assert (repeat[P[5]]["reports"], repeat[P[5]]["reporters"], repeat[P[5]]["open"], repeat[P[5]]["confirmed"]) == (3, 3, 3, 0), repeat[P[5]]
    assert (repeat[P[6]]["reports"], repeat[P[6]]["reporters"]) == (3, 1), repeat[P[6]]
    assert rep["repeat"][0]["id"] == P[5] or rep["repeat"][0]["reports"] >= rep["repeat"][1]["reports"], rep["repeat"]
    assert repeat[P[5]]["name"] == f"@u{P[5]}" and "reporter" not in repeat[P[5]] and "reporter_id" not in repeat[P[5]], repeat[P[5]]
    assert (await get(HELPER, "/reports?kind=closed")).json()["repeat"] == []
    first = next(r for r in rep["items"] if r["target"]["id"] == P[5])
    assert (await client.post(f"/bot-admin/api/reports/{first['id']}", headers=h[HELPER], json={"action": "take"})).status_code == 200
    assert (await badges(HELPER)).json() == {"reports": 7}                                    # взятая в работу уходит из «новых»

    # ── Люди, которым нужно внимание: бан важнее жалоб, контроль виден, дублей нет ──
    from services import global_moderation, staff_watch as staff_watch_service
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        await global_moderation.ensure_schema(db)
        await staff_watch_service.ensure_schema(db)
        await db.execute("INSERT INTO chat_blacklist (chat_id, user_id, reason, added_by, expires_at) "
                         "VALUES (0, ?, 'спам-рассылка', ?, NULL)", (P[5], HELPER))
        await staff_watch_service.add(db, P[3], HELPER, "новичок в мутных историях")
    assert (await get(P[1], "/people/attention")).status_code == 403
    attn = (await get(HELPER, "/people/attention")).json()
    by_id = {x["id"]: x for x in attn["items"]}
    assert [x["id"] for x in attn["items"]][0] == P[5], attn["items"]                                 # бан впереди
    assert by_id[P[5]]["flag_kind"] == "bad" and "во всех чатах" in by_id[P[5]]["flag"], by_id[P[5]]  # и без дубля с жалобами
    assert by_id[P[6]]["flag_kind"] == "warn" and by_id[P[6]]["flag"] == "⚠️ жалоб: 3", by_id[P[6]]
    assert by_id[P[3]]["flag_kind"] == "warn" and "контроле" in by_id[P[3]]["flag"], by_id[P[3]]
    assert by_id[P[5]]["avatar"].startswith("/bot-admin/avatar/"), by_id[P[5]]
    assert (await get(HELPER, "/people/attention?limit=2")).json()["total"] >= 3                      # limit режет показ, не поиск


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(prepare())
    loop.run_until_complete(checks())
    print("OK: bot admin chat settings, attention list and report badges on PostgreSQL")


main()
