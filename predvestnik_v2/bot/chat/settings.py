"""Глобальные настройки бота (таблица bot_settings, значения — JSON)."""
from __future__ import annotations

import json

TRANSFERABLE_KEY = "transfer_currencies"
# Зарники (премиальная валюта за Stars) и эссенцию переводить нельзя никогда.
NEVER_TRANSFERABLE = frozenset({"zarniki", "essence"})
DEFAULT_TRANSFERABLE = ("mora", "diamonds")


async def get_json(db, key: str, default):
    async with db.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)) as cur:
        row = await cur.fetchone()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except ValueError:
        return default


async def set_json(db, key: str, value, actor_id: int) -> None:
    await db.execute(
        "INSERT INTO bot_settings (key, value, updated_by) VALUES (?, ?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, updated_at = NOW()",
        (key, json.dumps(value, ensure_ascii=False), actor_id))


async def transferable(db) -> tuple[str, ...]:
    codes = await get_json(db, TRANSFERABLE_KEY, list(DEFAULT_TRANSFERABLE))
    return tuple(c for c in codes if c not in NEVER_TRANSFERABLE)
