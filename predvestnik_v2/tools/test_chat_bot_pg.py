#!/usr/bin/env python3
"""Новый чат-бот на настоящем PostgreSQL: учёт сообщений, «бот топ», ранги.

Запуск: python tools/test_chat_bot_pg.py --dsn postgresql://... (пустая тестовая БД!)
"""
import argparse
import asyncio
import os
import sys
from types import SimpleNamespace

ap = argparse.ArgumentParser()
ap.add_argument("--dsn", required=True)
dsn = ap.parse_args().dsn
os.environ["DATABASE_URL"] = dsn
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ["DEVELOPER_ID"] = "42"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def msg(uid, chat, username, title="Тест"):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=uid, is_bot=False, username=username),
        chat=SimpleNamespace(id=chat, type="supergroup", title=title),
    )


async def main():
    from infrastructure.database import create_pool, get_pool
    from infrastructure.pg_adapter import PGAdapter
    from bot.core.database import init_db
    from bot.chat.schema import ensure_chat_schema
    from bot.chat.tracking import record_message
    from bot.chat import ranks, top

    await create_pool()
    await init_db()
    await ensure_chat_schema()
    await ensure_chat_schema()   # повторный запуск безопасен
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        for _ in range(3):
            await record_message(db, msg(1001, -100, "alpha"))
        await record_message(db, msg(1002, -100, "beta"))
        await record_message(db, msg(1002, -200, "beta", "Другой"))

        text, pages = await top.build(db, "c", "d", 0, -100)
        assert pages == 1 and text.index("alpha") < text.index("beta"), text
        assert "3" in text
        text, _ = await top.build(db, "g", "w", 0, -100)
        assert "beta" in text and "alpha" in text
        text, _ = await top.build(db, "k", "d", 0, -100)
        assert text.index("Тест") < text.index("Другой"), text
        text, _ = await top.build(db, "c", "lw", 0, -100)
        assert "Пока тихо" in text

        # Ранги: перенос старого local_rank, владелец, права.
        await db.execute("UPDATE user_chat_stats SET local_rank = 1 WHERE user_tg_id = 1001")
        assert await ranks.get_rank(db, -100, 1001) == 4
        await ranks.store_rank(db, -100, 1002, 6)
        assert await ranks.get_rank(db, -100, 1002) == 6
        await ranks.set_owner(db, -100, 1001)
        assert await ranks.get_rank(db, -100, 1001) == ranks.OWNER
        assert await ranks.can(db, -100, 1002, "ban") and not await ranks.can(db, -100, 1002, "rights")
        await ranks.set_right(db, -100, "ban", 7, 1001)
        assert not await ranks.can(db, -100, 1002, "ban")
        assert await ranks.can(db, -100, 42, "rights")          # разработчик
        assert await ranks.get_rank(db, -100, 42) == ranks.DEV_LEVEL
    print("OK: chat bot on PostgreSQL")


asyncio.run(main())
