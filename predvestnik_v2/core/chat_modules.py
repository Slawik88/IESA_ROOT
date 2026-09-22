"""Canonical registry for current Telegram chat product modules."""
from __future__ import annotations

from typing import Final


CHAT_MODULES: Final = {
    "module_mafia": {"icon": "🔫", "name": "Мафия", "description": "Групповая игра с фазами и голосованием.", "default_enabled": True},
    "module_rhythm": {"icon": "🎵", "name": "Ритм", "description": "Чатовый вход и прогресс режима Ритм.", "default_enabled": True},
    "module_pets": {"icon": "🐾", "name": "Питомцы", "description": "Карточки, походы и экспедиции питомцев.", "default_enabled": True},
    "module_quests": {"icon": "🧭", "name": "Квесты", "description": "Просмотр текущих дневных и недельных заданий.", "default_enabled": True},
    "module_warps": {"icon": "🤝", "name": "Социальные действия", "description": "Варпы и реакции между участниками.", "default_enabled": True},
    "module_echo": {"icon": "🔔", "name": "Эхо", "description": "Ручной чат-ивент без наград и личного спама.", "default_enabled": False},
}

CHAT_MODULE_KEYS: Final = frozenset(CHAT_MODULES)


def chat_module_default(module_key: str) -> bool:
    if module_key not in CHAT_MODULES:
        raise ValueError(f"unknown chat module: {module_key}")
    return bool(CHAT_MODULES[module_key]["default_enabled"])
