"""Canonical registry for current Telegram chat product modules."""
from __future__ import annotations

from typing import Final


CHAT_MODULES: Final = {
    "module_mafia": {"icon": "🔫", "name": "Мафия", "description": "Групповая игра с фазами и голосованием."},
    "module_rhythm": {"icon": "🎵", "name": "Ритм", "description": "Чатовый вход и прогресс режима Ритм."},
    "module_pets": {"icon": "🐾", "name": "Питомцы", "description": "Карточки, походы и экспедиции питомцев."},
    "module_quests": {"icon": "🧭", "name": "Квесты", "description": "Просмотр текущих дневных и недельных заданий."},
    "module_warps": {"icon": "🤝", "name": "Социальные действия", "description": "Варпы и реакции между участниками."},
    "module_echo": {"icon": "🔔", "name": "Эхо", "description": "Ручной чат-ивент без наград и личного спама."},
}

CHAT_MODULE_KEYS: Final = frozenset(CHAT_MODULES)
