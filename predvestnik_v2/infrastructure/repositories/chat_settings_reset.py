"""Возврат настроек чата к стандарту — единая логика для бота и мини-аппа.

Сброс идёт через те же каналы, что и точечные правки: модули —
chat_module_audit.set_chat_module (append-only чек по каждому модулю),
скалярные настройки — update_chat_settings + chat_settings_audit.
Скрытые служебные колонки (shield_duration_days, notif_* и т.п.) не трогаются.
"""
from __future__ import annotations

from core.chat_modules import CHAT_MODULES, chat_module_default
from core.chat_settings_defaults import CHAT_SETTING_DEFAULTS
from infrastructure.repositories import chat_module_audit, chat_settings_audit
from infrastructure.repositories.moderation import get_chat_settings, update_chat_settings


async def reset_chat_settings_to_defaults(db, *, chat_id: int, actor_id: int,
                                          source: str) -> dict:
    settings = await get_chat_settings(db, chat_id)

    settings_changed = 0
    for key, default in CHAT_SETTING_DEFAULTS.items():
        raw = settings.get(key, default)
        before = default if raw is None else int(raw)
        if before == int(default):
            continue
        await update_chat_settings(db, chat_id, **{key: int(default)})
        await chat_settings_audit.record(
            db, chat_id=chat_id, setting_key=key, before=before, after=int(default),
            actor_id=actor_id, source=source,
        )
        settings_changed += 1

    modules_changed = 0
    for module_key in CHAT_MODULES:
        default = int(chat_module_default(module_key))
        raw = settings.get(module_key)
        before = default if raw is None else int(bool(raw))
        if before == default:
            continue
        await chat_module_audit.set_chat_module(
            db, chat_id=chat_id, module_key=module_key, enabled=bool(default),
            actor_id=actor_id, source=source,
        )
        modules_changed += 1

    return {"modules_changed": modules_changed, "settings_changed": settings_changed}
