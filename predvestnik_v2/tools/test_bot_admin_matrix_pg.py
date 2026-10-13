"""ADM-02 этап 3: права ролей через API — матрица меняет доступ сотрудников, потолок и подтверждение.

Запуск: python tools/test_bot_admin_matrix_pg.py --dsn postgresql://... (пустая тестовая БД!)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

ap = argparse.ArgumentParser()
ap.add_argument("--dsn", required=True)
os.environ["DATABASE_URL"] = ap.parse_args().dsn
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ["DEVELOPER_ID"] = "1001"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from types import SimpleNamespace  # noqa: E402

DEV, JUNIOR, HELPER, SENIOR, CODER, TESTER, P1, P2, P3, P4 = 1001, 2002, 3003, 4004, 5005, 1005, 7001, 7002, 7003, 7004
CHAT = -100


class FakeBot:
    async def me(self):
        return SimpleNamespace(id=999, username="bot")

    async def ban_chat_member(self, *a, **k): pass
    async def unban_chat_member(self, *a, **k): pass
    async def restrict_chat_member(self, *a, **k): pass
    async def get_chat(self, chat_id): return SimpleNamespace(permissions=None)


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
    from services import admin_security

    await create_pool()
    await init_db()
    await ensure_runtime_schema(get_pool())
    await ensure_chat_schema()
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        for uid, rank in ((DEV, 0), (JUNIOR, 2), (HELPER, 3), (SENIOR, 4), (CODER, 5), (TESTER, 1), (P1, 0), (P2, 0), (P3, 0), (P4, 0)):
            await db.execute("INSERT INTO users (user_tg_id, user_tg_username, bot_rank) VALUES (?, ?, ?)", (uid, f"u{uid}", rank))
        await db.execute("INSERT INTO chat_settings (chat_id, chat_title) VALUES (?, 'Чат')", (CHAT,))
        for uid in (P1, P2, P3, P4):
            await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, is_left) VALUES (?, ?, FALSE)", (uid, CHAT))
    people.set_bot(FakeBot())
    client = Client(main.app)
    tok = {uid: {"x-session-token": create_session_token(uid)} for uid in (DEV, JUNIOR, HELPER, SENIOR, CODER, TESTER)}
    base = "/bot-admin/api"
    admin_security.reset_limits()

    async def get(who, path):
        return await client.get(base + path, headers=tok[who])

    async def post(who, path, **body):
        admin_security.reset_limits()
        return await client.post(base + path, headers=tok[who], json=body)

    async def ban(who, uid):
        return (await post(who, f"/player/{uid}/action", action="ban", chat_id=CHAT, minutes=10)).status_code

    async def setm(key, rank, confirm):
        return await post(DEV, "/access/matrix", key=key, min_rank=rank, confirm=confirm)

    # ── по умолчанию как в коде ──
    assert await ban(HELPER, P1) == 403 and await ban(SENIOR, P1) == 200
    assert (await get(HELPER, "/metrics")).status_code == 403
    assert "metrics" not in [s["key"] for s in (await get(HELPER, "/me")).json()["sections"]]

    # ── матрицу видит и меняет только создатель ──
    for who in (JUNIOR, HELPER, SENIOR):
        assert (await get(who, "/access/matrix")).status_code == 403
        assert (await post(who, "/access/matrix", key="action:ban", min_rank=3, confirm="хелпер")).status_code == 403
    m = (await get(DEV, "/access/matrix")).json()
    keys = {i["key"]: i for i in m["items"]}
    assert keys["action:ban"]["current"] == 4 and keys["action:ban"]["default"] == 4 and not keys["action:ban"]["changed"], keys["action:ban"]
    assert "action:balance" not in keys and "action:rank" not in keys and "section:settings" not in keys
    assert [r["rank"] for r in m["roles"]] == [2, 3, 4, 5]
    assert "access" not in [s["key"] for s in (await get(HELPER, "/me")).json()["sections"]]
    assert "access" in [s["key"] for s in (await get(DEV, "/me")).json()["sections"]]

    # ── подтверждение вводом названия роли, пол и потолок ──
    assert (await setm("action:ban", 3, "")).status_code == 400
    assert (await setm("action:ban", 3, "старший хелпер")).status_code == 400
    assert (await setm("action:ban", 1, "тестер")).status_code == 400
    assert (await setm("action:ban", 6, "создатель")).status_code == 400
    assert (await setm("action:balance", 3, "хелпер")).status_code == 400
    assert (await setm("action:nonsense", 3, "хелпер")).status_code == 400
    assert await ban(HELPER, P2) == 403

    # ── изменение действует сразу ──
    r = await setm("action:ban", 3, "хелпер")
    assert r.status_code == 200 and r.json()["current"] == 3, r.text
    assert await ban(HELPER, P2) == 200
    assert (await get(DEV, "/access/matrix")).json()["items"][0] is not None
    card = (await get(HELPER, f"/chat/{CHAT}")).json()
    assert "ban" in [a["key"] for a in card["actions"]["member"]]
    assert await ban(JUNIOR, P3) == 403
    # пониже хелпера, но не ниже пола
    assert (await setm("action:ban", 2, "младший хелпер")).status_code == 200
    assert await ban(JUNIOR, P3) == 200
    # цель не выше по роли: матрица этого не отменяет
    assert (await post(JUNIOR, f"/player/{HELPER}/action", action="ban", chat_id=CHAT)).status_code in (403, 404)

    # ── раздел ──
    assert (await setm("section:metrics", 3, "хелпер")).status_code == 200
    assert (await get(HELPER, "/metrics")).status_code == 200
    assert "metrics" in [s["key"] for s in (await get(HELPER, "/me")).json()["sections"]]
    assert (await get(JUNIOR, "/metrics")).status_code == 403

    # ── сброс ──
    assert (await setm("action:ban", None, "сброс")).status_code == 200
    assert (await setm("section:metrics", None, "сброс")).status_code == 200
    assert (await get(HELPER, "/metrics")).status_code == 403
    admin_security.reset_limits()
    assert await ban(HELPER, P3) == 403

    # ── строка в БД сверх потолка или вне списка ничего не открывает ──
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        await db.execute("INSERT INTO admin_role_grants (key, min_rank, updated_by) VALUES ('action:global_ban', 2, 0)")
        await db.execute("INSERT INTO admin_role_grants (key, min_rank, updated_by) VALUES ('section:settings', 2, 0)")
        await db.execute("INSERT INTO admin_role_grants (key, min_rank, updated_by) VALUES ('action:kick', 1, 0)")
        await db.execute("INSERT INTO admin_role_grants (key, min_rank, updated_by) VALUES ('action:mute', 9, 0)")
        await db.execute("INSERT INTO admin_role_grants (key, min_rank, updated_by) VALUES ('section:reports', 1, 0)")
    assert (await post(HELPER, f"/player/{P3}/action", action="global_ban", reason="x", confirm=str(P3))).status_code == 403
    assert (await get(HELPER, "/settings")).status_code == 403
    assert (await post(JUNIOR, f"/player/{P3}/action", action="kick", chat_id=CHAT)).status_code == 200   # пол 2: ужато, но не закрыто
    assert (await post(CODER, f"/player/{P4}/action", action="mute", chat_id=CHAT, minutes=5)).status_code == 200   # потолок 5: разработчик проходит
    assert (await get(TESTER, "/reports")).status_code == 403   # пол 2: тестер раздел не получает, как ни записано в БД
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        async with db.execute("SELECT COUNT(*) FROM bot_admin_actions WHERE action = 'grant' AND actor_id = ?", (DEV,)) as cur:
            assert (await cur.fetchone())[0] == 5   # три изменения и два сброса попали в журнал


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run())
    print("OK: role matrix over API (creator-only, typed confirm, floor/ceiling, immediate effect, reset) on PostgreSQL")


main()
