"""Ники старого бота удалены (владелец, 2026-10-21): бот везде пишет имя из Telegram.

Шаг старта (bot/startup_schema.py), без возвратов — компенсацию игроки получили раньше: жетоны смены ника
(zarniki_nickname_token) убираются из инвентарей, таблица ников и счётчики смены ника — из базы.
Повторный запуск ничего не делает."""
from __future__ import annotations

from loguru import logger

STATEMENTS = (
    "DROP TABLE IF EXISTS user_nicknames",
    "ALTER TABLE user_chat_stats DROP COLUMN IF EXISTS nickname_changes_count",
    "ALTER TABLE user_chat_stats DROP COLUMN IF EXISTS nickname_changes_reset_at",
)


async def ensure_tables(db) -> None:
    async with db.execute("DELETE FROM inventory WHERE item_id = 'zarniki_nickname_token' RETURNING user_id") as cur:
        removed = len(await cur.fetchall())
    if removed:
        logger.info(f"Жетоны смены ника удалены у {removed} игроков (без возврата)")
    for sql in STATEMENTS:
        await db.execute(sql)
