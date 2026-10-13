"""ADM-02: права ролей в БД — запись только создателем, потолок при чтении, журнал.

Запуск: python tools/test_bot_admin_access_pg.py --dsn postgresql://... (пустая тестовая БД!)
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

from fastapi import HTTPException  # noqa: E402


async def run():
    from infrastructure.database import create_pool, get_pool
    from infrastructure.pg_adapter import PGAdapter
    from bot.core.database import init_db
    from bot.startup_schema import ensure_runtime_schema
    from services import admin_access as acc, admin_people

    await create_pool()
    await init_db()
    await ensure_runtime_schema(get_pool())
    creator, developer = acc.staff_principal(1001, 6), acc.staff_principal(2002, 5)
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        assert await acc.load_grants(db) == {}

        await acc.set_grant(db, creator, "action:ban", 3)
        await acc.set_grant(db, creator, "section:metrics", 2)
        grants = await acc.load_grants(db)
        assert grants == {"action:ban": 3, "section:metrics": 2}, grants
        assert acc.effective_min("action:ban", 4, grants) == 3
        await acc.set_grant(db, creator, "action:ban", 4)   # перезапись, не вторая строка
        assert (await acc.load_grants(db))["action:ban"] == 4

        for who, key, rank, code in ((developer, "action:ban", 3, 403), (creator, "action:balance", 3, 400),
                                     (creator, "action:ban", 1, 400), (creator, "action:ban", 6, 400),
                                     (acc.owner_principal(7, [-1]), "action:ban", 3, 403)):
            try:
                await acc.set_grant(db, who, key, rank)
            except HTTPException as exc:
                assert exc.status_code == code, (key, rank, exc.status_code)
            else:
                raise AssertionError(f"{key}={rank} не должно записываться")
        assert (await acc.load_grants(db))["action:ban"] == 4

        # строка сверх потолка (ручной SQL / старая версия) ужимается при чтении
        await db.execute("INSERT INTO admin_role_grants (key, min_rank, updated_by) VALUES ('action:ban', 1, 0) "
                         "ON CONFLICT (key) DO UPDATE SET min_rank = 1")
        await db.execute("INSERT INTO admin_role_grants (key, min_rank, updated_by) VALUES ('action:balance', 2, 0)")
        grants = await acc.load_grants(db)
        assert acc.effective_min("action:ban", 4, grants) == acc.FLOOR
        assert acc.effective_min("action:balance", 5, grants) == 5

        await acc.set_grant(db, creator, "action:ban", None)   # назад к значению по умолчанию
        assert "action:ban" not in await acc.load_grants(db)
        async with db.execute("SELECT COUNT(*) FROM bot_admin_actions WHERE action = 'grant' AND actor_id = 1001") as cur:
            assert (await cur.fetchone())[0] == 4   # изменения: ban 3, metrics 2, ban 4, сброс ban


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run())
    print("OK: admin role grants on PostgreSQL (creator-only writes, ceiling on read, audit)")


main()
