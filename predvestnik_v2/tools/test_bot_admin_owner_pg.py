"""ADM-02 этап 2: доступ владельцев чатов — выключатель, свежее владение, область, цели, «канарейки» данных.

Запуск: python tools/test_bot_admin_owner_pg.py --dsn postgresql://... (пустая тестовая БД!)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

ap = argparse.ArgumentParser()
ap.add_argument("--dsn", required=True)
os.environ["DATABASE_URL"] = ap.parse_args().dsn
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ["DEVELOPER_ID"] = "1001"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from types import SimpleNamespace  # noqa: E402

DEV, STAFF, OWN_A, OWN_B, STRANGER, STALE, P1, P2, P3 = 1001, 3003, 5001, 5002, 5003, 5004, 6001, 6002, 6003
A, B, LEFT, OLD, OVR = -100, -200, -400, -300, -500
CANARIES = ("TitleBBB", "secretB", "STAFFNOTE", "777777", "-200", "canary_p2")


class FakeBot:
    """Telegram: создатели чатов задаются словарём; down=True — Telegram недоступен."""
    def __init__(self):
        self.creators = {A: OWN_A, B: OWN_B, LEFT: OWN_A, OLD: 9999, OVR: OWN_B}
        self.down = False
        self.admin_calls = []
        self.actions = []

    async def me(self):
        return SimpleNamespace(id=999, username="predvestnik_bot")

    async def get_chat_administrators(self, chat_id):
        self.admin_calls.append(chat_id)
        await asyncio.sleep(0.05)
        if self.down:
            raise RuntimeError("Telegram is down")
        return [SimpleNamespace(status="creator", user=SimpleNamespace(id=self.creators[chat_id]))]

    async def get_chat(self, chat_id):
        return SimpleNamespace(permissions=None)

    async def _rec(self, name, chat_id, user_id):
        self.actions.append((name, chat_id, user_id))

    async def restrict_chat_member(self, chat_id, user_id, permissions=None, until_date=None):
        await self._rec("restrict", chat_id, user_id)

    async def ban_chat_member(self, chat_id, user_id, until_date=None):
        await self._rec("ban", chat_id, user_id)

    async def unban_chat_member(self, chat_id, user_id, only_if_banned=False):
        await self._rec("unban", chat_id, user_id)

    async def send_message(self, chat_id, text, **kw):
        await self._rec("send", chat_id, 0)


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
    import FastAPI.main as main
    from services import owner_access, admin_security

    await create_pool()
    await init_db()
    await ensure_runtime_schema(get_pool())
    await ensure_chat_schema()
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        for uid, name, rank in ((DEV, "dev", 0), (STAFF, "helper", 3), (OWN_A, "ownA", 0), (OWN_B, "ownB", 0),
                                (STRANGER, "stranger", 0), (STALE, "stale", 0), (P1, "p1", 0), (P2, "canary_p2", 0), (P3, "p3", 0)):
            await db.execute("INSERT INTO users (user_tg_id, user_tg_username, bot_rank) VALUES (?, ?, ?)", (uid, name, rank))
        await db.execute("UPDATE users SET user_balance_mora = 777777 WHERE user_tg_id = ?", (P1,))
        from services import staff_notes
        await staff_notes.ensure_schema(db) if hasattr(staff_notes, "ensure_schema") else None
        await staff_notes.add(db, P1, STAFF, "STAFFNOTE про игрока")
        for cid, title, owner, left, override in ((A, "Чат А", OWN_A, False, None), (B, "TitleBBB", OWN_B, False, None),
                                                   (LEFT, "Ушли", OWN_A, True, None), (OLD, "Старый", STALE, False, None),
                                                   (OVR, "Спорный", OWN_B, False, STRANGER)):
            await db.execute("INSERT INTO chat_settings (chat_id, chat_title, owner_id, owner_override, bot_left_at) "
                             "VALUES (?, ?, ?, ?, CASE WHEN ? THEN NOW() END)", (cid, title, owner, override, left))
        for uid, cid in ((P1, A), (P1, B), (P2, B), (P3, A), (STAFF, A), (OWN_A, A)):
            await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, is_left) VALUES (?, ?, FALSE)", (uid, cid))
        await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, is_left) VALUES (?, ?, TRUE)", (P2, A))
        await db.execute("INSERT INTO chat_blacklist (chat_id, user_id, reason, added_by) VALUES (?, ?, 'secretB', ?)", (B, P2, OWN_B))
        await db.execute("INSERT INTO user_warnings (chat_id, user_id, admin_id, reason) VALUES (?, ?, ?, 'флуд')", (A, P1, OWN_A))

    bot = FakeBot()
    people.set_bot(bot)
    client = Client(main.app)
    tok = {uid: {"x-session-token": create_session_token(uid)} for uid in (DEV, STAFF, OWN_A, OWN_B, STRANGER, STALE, P1)}
    base = "/bot-admin/api"

    async def get(who, path):
        return await client.get(base + path, headers=tok.get(who, {}))

    async def post(who, path, **body):
        return await client.post(base + path, headers=tok.get(who, {}), json=body)

    def fresh():
        owner_access.reset_cache()
        admin_security.reset_limits()
        bot.admin_calls.clear()

    # ── выключатель: по умолчанию закрыто ──
    fresh()
    for who in (OWN_A, OWN_B, STRANGER):
        r = await get(who, "/owner/me")
        assert r.status_code == 403, (who, r.status_code, r.text)
    assert not bot.admin_calls, "Telegram не должен опрашиваться, пока вход закрыт"
    assert (await get(None, "/owner/me")).status_code == 401

    # ── включает только создатель ──
    assert (await post(STAFF, "/access/owners", enabled=True)).status_code == 403
    assert (await post(OWN_A, "/access/owners", enabled=True)).status_code in (401, 403)
    r = await post(DEV, "/access/owners", enabled=True)
    assert r.status_code == 200 and r.json()["enabled"] is True, r.text
    assert (await get(DEV, "/access/owners")).json()["enabled"] is True

    # ── кто входит ──
    fresh()
    me = (await get(OWN_A, "/owner/me")).json()
    assert [c["id"] for c in me["chats"]] == [A], me   # LEFT: бот вышел; ни чужих, ни спорных
    ids_b = sorted(c["id"] for c in (await get(OWN_B, "/owner/me")).json()["chats"])
    assert ids_b == sorted([B, OVR]), ids_b   # OVR: создатель по Telegram — OWN_B; override входа не даёт и не отнимает
    assert (await get(STRANGER, "/owner/me")).status_code == 403   # owner_override сам по себе входа не даёт
    assert (await get(STALE, "/owner/me")).status_code == 403      # в БД владелец, а Telegram говорит иначе
    assert (await get(STAFF, "/owner/me")).status_code == 403      # у сотрудника нет своих чатов
    assert (await get(P1, "/owner/me")).status_code == 403

    # ── TTL и схлопывание параллельных проверок ──
    fresh()
    await asyncio.gather(*(get(OWN_A, "/owner/me") for _ in range(5)))
    assert bot.admin_calls.count(A) == 1, bot.admin_calls
    await get(OWN_A, "/owner/me")
    assert bot.admin_calls.count(A) == 1, "повторный запрос в пределах TTL не идёт в Telegram"

    # ── область и канарейки ──
    fresh()
    r = await get(OWN_A, f"/owner/chat/{A}")
    assert r.status_code == 200, r.text
    dump = json.dumps(r.json(), ensure_ascii=False)
    for canary in CANARIES:
        assert canary not in dump, (canary, dump)
    assert r.json()["members"] == 4 and r.json()["sanctions"]["warns"][0]["count"] == 1, r.json()
    for path in (f"/owner/chat/{B}", f"/owner/chat/{LEFT}", f"/owner/chat/{OVR}"):
        assert (await get(OWN_A, path)).status_code == 403, path
    assert (await post(OWN_A, f"/owner/chat/{B}/action", action="close")).status_code == 403
    assert (await post(OWN_A, f"/owner/chat/{B}/member/{P1}/action", action="mute", minutes=10)).status_code == 403
    assert bot.actions == [], bot.actions

    # ── действия в своём чате ──
    r = await post(OWN_A, f"/owner/chat/{A}/action", action="close")
    assert r.status_code == 200, r.text
    r = await post(OWN_A, f"/owner/chat/{A}/action", action="warn_limit", value=99)
    assert r.status_code == 400
    assert (await post(OWN_A, f"/owner/chat/{A}/action", action="message", text="hi")).status_code == 400   # «от бота» не даём
    r = await post(OWN_A, f"/owner/chat/{A}/member/{P1}/action", action="mute", minutes=10, reason="флуд")
    assert r.status_code == 200 and ("restrict", A, P1) in bot.actions, r.text
    r = await post(OWN_A, f"/owner/chat/{A}/member/{P3}/action", action="warn", reason="спам")
    assert r.status_code == 200, r.text
    assert (await post(OWN_A, f"/owner/chat/{A}/member/{P3}/action", action="unmute")).status_code == 200

    # ── цели действий ──
    cases = (
        (OWN_A, "mute", "к себе"), (STAFF, "mute", "сотрудник бота"), (DEV, "ban", "разработчик"), (999, "kick", "сам бот"),
        (P2, "ban", "вышел из чата, санкции в этом чате нет"),   # P2 в чате А со статусом is_left, санкции здесь нет
        (7777777, "mute", "неизвестный"),
    )
    for uid, action, why in cases:
        r = await post(OWN_A, f"/owner/chat/{A}/member/{uid}/action", action=action, minutes=5)
        assert r.status_code in (403, 404), (why, r.status_code, r.text)
    before = len(bot.actions)
    for action in ("balance", "rank", "global_ban", "message", "leave", "mark_grant"):
        assert (await post(OWN_A, f"/owner/chat/{A}/member/{P1}/action", action=action)).status_code == 400, action
    assert len(bot.actions) == before
    # снять санкцию с того, кто уже вышел, можно, если она в этом чате есть
    async with get_pool().acquire() as conn:
        await PGAdapter(conn).execute("INSERT INTO chat_blacklist (chat_id, user_id, reason, added_by) VALUES (?, ?, 'x', ?)", (A, P2, OWN_A))
    assert (await post(OWN_A, f"/owner/chat/{A}/member/{P2}/action", action="unban")).status_code == 200

    # ── владелец закрыт от всего, что для сотрудников ──
    staff_gets = ("/search?q=p1", f"/player/{P1}", f"/chat/{B}", f"/chat/{A}", "/metrics", "/metrics/export", "/journal",
                  f"/switches?chat_id={B}", "/reports", "/promo", "/chats", "/settings", "/health", "/broadcasts", "/badges",
                  "/me", "/logins", "/chats/attention", "/access/owners")
    for path in staff_gets:
        assert (await get(OWN_A, path)).status_code in (401, 403), path
    for path, body in (("/players/bulk", {"action": "watch", "ids": [P1]}), (f"/player/{P1}/action", {"action": "warn", "chat_id": A}),
                       (f"/chat/{A}/action", {"action": "close"}), ("/reports/bulk", {"action": "in_work", "ids": [1]}),
                       ("/switches", {"feature": "x", "chat_id": A}), ("/sessions/revoke", {}), ("/access/owners", {"enabled": False}),
                       ("/access/owners/block", {"user_id": OWN_A})):
        assert (await post(OWN_A, path, **body)).status_code in (401, 403), path

    # ── сбой Telegram = отказ, смена владельца и отзыв действуют сразу ──
    fresh()
    bot.down = True
    assert (await get(OWN_A, "/owner/me")).status_code == 403
    bot.down = False
    owner_access.reset_cache()
    assert (await get(OWN_A, "/owner/me")).status_code == 200
    bot.creators[A] = STRANGER   # чат передали
    owner_access.reset_cache()
    assert (await get(OWN_A, "/owner/me")).status_code == 403
    bot.creators[A] = OWN_A
    owner_access.reset_cache()
    assert (await get(OWN_A, "/owner/me")).status_code == 200
    assert (await post(DEV, "/access/owners/block", user_id=OWN_A, reason="тест")).status_code == 200
    assert (await get(OWN_A, "/owner/me")).status_code == 403   # без сброса кэша: отзыв работает сразу
    assert (await get(OWN_B, "/owner/me")).status_code == 200
    assert (await post(DEV, "/access/owners/block", user_id=OWN_A, blocked=False)).status_code == 200
    assert (await get(OWN_A, "/owner/me")).status_code == 200

    # ── лимит частоты распространяется и на владельцев ──
    admin_security.reset_limits()
    codes = [(await post(OWN_A, f"/owner/chat/{A}/member/{P3}/action", action="warn")).status_code for _ in range(62)]
    assert 429 in codes and codes[0] == 200, codes[:3]

    # ── выключили — закрыто сразу ──
    assert (await post(DEV, "/access/owners", enabled=False)).status_code == 200
    assert (await get(OWN_A, "/owner/me")).status_code == 403
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        async with db.execute("SELECT COUNT(*) FROM bot_admin_actions WHERE action IN ('owner_access', 'owner_block')") as cur:
            assert (await cur.fetchone())[0] == 4   # включили, отозвали, вернули, выключили
        async with db.execute("SELECT COUNT(*) FROM bot_admin_actions WHERE chat_id = ? AND details->>'as' = 'owner'", (A,)) as cur:
            assert (await cur.fetchone())[0] >= 5


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run())
    print("OK: owner access (switch, fresh ownership, scope, targets, canaries, rate limit) on PostgreSQL")


main()
