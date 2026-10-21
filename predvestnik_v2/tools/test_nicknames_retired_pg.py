#!/usr/bin/env python3
"""Ники старого бота удалены: шаг старта убирает жетоны смены ника, таблицу ников и счётчики; повтор ничего не ломает.

Запуск: python tools/test_nicknames_retired_pg.py --dsn postgresql://...  (локальная тестовая база)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--dsn", required=True)
os.environ["DATABASE_URL"] = ap.parse_args().dsn
os.environ.setdefault("BOT_TOKEN", "123456:offline-nicknames")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

USER = 985101


async def exists(db, sql: str, args=()) -> bool:
    async with db.execute(sql, args) as cur:
        return bool((await cur.fetchone())[0])


async def main() -> None:
    from infrastructure.database import create_pool, get_pool
    from infrastructure.pg_adapter import PGAdapter
    from bot.core.database import init_db
    from infrastructure.repositories import nicknames_retired
    await create_pool()
    await init_db()
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        # как в проде до выкатки: таблица ников, счётчики, жетоны у игрока рядом с другим предметом
        await db.execute("CREATE TABLE IF NOT EXISTS user_nicknames (user_id BIGINT, chat_id BIGINT, nickname TEXT NOT NULL, PRIMARY KEY (user_id, chat_id))")
        await db.execute("ALTER TABLE user_chat_stats ADD COLUMN IF NOT EXISTS nickname_changes_count INTEGER DEFAULT 0")
        await db.execute("ALTER TABLE user_chat_stats ADD COLUMN IF NOT EXISTS nickname_changes_reset_at TIMESTAMP DEFAULT NOW()")
        await db.execute("INSERT INTO user_nicknames VALUES (?, -1, 'своего фаната') ON CONFLICT DO NOTHING", (USER,))
        await db.execute("DELETE FROM inventory WHERE user_id = ?", (USER,))
        await db.execute("INSERT INTO inventory(user_id, item_id, quantity) VALUES (?, 'zarniki_nickname_token', 3), (?, 'soul_shard', 7)", (USER, USER))
        try:
            for _ in range(2):   # повторный старт — то же самое
                await nicknames_retired.ensure_tables(db)
            assert not await exists(db, "SELECT to_regclass('user_nicknames') IS NOT NULL")
            assert not await exists(db, "SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'user_chat_stats' "
                                        "AND column_name IN ('nickname_changes_count', 'nickname_changes_reset_at')")
            async with db.execute("SELECT item_id, quantity FROM inventory WHERE user_id = ? ORDER BY item_id", (USER,)) as cur:
                assert [tuple(r) for r in await cur.fetchall()] == [("soul_shard", 7)]   # жетон ушёл без возврата, остальное на месте
        finally:
            await db.execute("DELETE FROM inventory WHERE user_id = ?", (USER,))
    print("nicknames retired: OK")


if __name__ == "__main__":
    asyncio.run(main())
