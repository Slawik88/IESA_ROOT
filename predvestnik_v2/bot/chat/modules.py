"""Тумблеры разделов: глобальный флаг фичи (system_flags) и модуль чата
(chat_settings.module_* + global_module_toggles). Логика как была у игр."""
from __future__ import annotations

from core.chat_modules import CHAT_MODULE_KEYS, chat_module_default


async def feature_enabled(db, key: str) -> bool:
    from infrastructure.repositories import system_flags
    return await system_flags.is_enabled(db, key)


async def module_disabled_reason(db, chat_id: int, module_key: str) -> str | None:
    """Почему модуль выключен в чате (или глобально); None — включён."""
    if module_key not in CHAT_MODULE_KEYS:
        raise ValueError(f"unknown chat module: {module_key}")
    async with db.execute(f"SELECT {module_key} FROM chat_settings WHERE chat_id = ?", (chat_id,)) as cur:
        row = await cur.fetchone()
    if row is not None and row[0] == 0:
        return "Этот раздел временно недоступен в данном чате."
    async with db.execute(
        "SELECT enabled, disabled_reason FROM global_module_toggles WHERE module_key = ?", (module_key,)
    ) as cur:
        row = await cur.fetchone()
    enabled = bool(row[0]) if row is not None else chat_module_default(module_key)
    if not enabled:
        return "Этот раздел пока не включён глобально." if row is None else str(row[1] or "Этот раздел временно отключён глобально.")
    return None
