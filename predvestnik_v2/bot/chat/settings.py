"""Глобальные настройки бота (таблица bot_settings, значения — JSON)."""
from __future__ import annotations

import json
from types import MappingProxyType

from core.economy_contract import CURRENCY_SPECS, CurrencySpec

# Эссенция живёт на своём счёте (skins_v3_essence_accounts, общий с Mini App),
# а не в общем леджере валют: здесь только её подпись для бота.
ESSENCE = CurrencySpec(code="essence", label="Эссенция", icon="🔮", balance_column="",
                       wallet_delta_column="", wallet_after_column="", role="cosmetics", display_decimals=0)
CURRENCY_VIEW = MappingProxyType({**CURRENCY_SPECS, "essence": ESSENCE})

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
