"""Canonical registry for current Telegram chat product modules.

Каждая запись — один точечный переключатель: администратор чата может
выключить одну механику в своём чате (chat_settings), а разработчик — для всей
сети (global_module_toggles). Группы — только для UI: enforcement никогда не
зависит от группы, ровно один модуль = ровно одна механика.
"""
from __future__ import annotations

from typing import Final


CHAT_MODULE_GROUPS: Final = {
    "core":     {"icon": "📦", "name": "Основное"},
    "stats":    {"icon": "📊", "name": "Статистика"},
    "profile":  {"icon": "👤", "name": "Профиль и валюта"},
    "family":   {"icon": "💍", "name": "Семья"},
    "interact": {"icon": "🤝", "name": "Взаимодействия"},
    "progress": {"icon": "🌱", "name": "Прогресс"},
    "games":    {"icon": "🎮", "name": "Игры"},
    "mod":      {"icon": "🛡", "name": "Модерация"},
    "purge":    {"icon": "🧹", "name": "Чистка"},
}

# Мастер-тумблер «Весь бот в чатах»: тихо гасит любые команды в чате.
MASTER_CHAT_MODULE: Final = "module_bot"

CHAT_MODULES: Final = {
    "module_bot": {"group": "core", "icon": "🚫", "name": "Весь бот в чатах",
                   "description": "Полный стоп: бот молчит на все команды.",
                   "default_enabled": True},
    "module_base": {"group": "core", "icon": "🧭", "name": "Основное",
                    "description": "Помощь, сайт, предметы и базовые команды.",
                    "default_enabled": True},
    "module_stats": {"group": "stats", "icon": "📊", "name": "Статистика",
                     "description": "Топы активности и список неактивных.",
                     "default_enabled": True},
    "module_profile": {"group": "profile", "icon": "👤", "name": "Профиль и валюта",
                       "description": "Карточка «я», ник, стрик и история кошелька.",
                       "default_enabled": True},
    "module_family": {"group": "family", "icon": "💍", "name": "Семья",
                      "description": "Браки, пары, общак и подарки.",
                      "default_enabled": True},
    "module_warps": {"group": "interact", "icon": "🤝", "name": "Варпы",
                     "description": "Варпы и реакции между участниками.",
                     "default_enabled": True},
    "module_dark_mora": {"group": "interact", "icon": "🌑", "name": "Тёмная Мора",
                         "description": "Архив тёмной Моры и теневые реликвии.",
                         "default_enabled": True},
    "module_echo": {"group": "interact", "icon": "🔔", "name": "Эхо",
                    "description": "Ручной чат-ивент без наград и личного спама.",
                    "default_enabled": False},
    "module_pets": {"group": "progress", "icon": "🐾", "name": "Питомцы",
                    "description": "Карточки, походы и экспедиции питомцев.",
                    "default_enabled": True},
    "module_quests": {"group": "progress", "icon": "🧭", "name": "Квесты",
                      "description": "Просмотр текущих дневных и недельных заданий.",
                      "default_enabled": True},
    "module_games": {"group": "games", "icon": "🎮", "name": "Игры",
                     "description": "Игровая витрина и переход в мини-игры.",
                     "default_enabled": True},
    "module_mafia": {"group": "games", "icon": "🕵️", "name": "Мафия",
                     "description": "Групповая игра с фазами и голосованием.",
                     "default_enabled": True},
    "module_rhythm": {"group": "games", "icon": "🎵", "name": "Ритм",
                      "description": "Чатовый вход и прогресс режима Ритм.",
                      "default_enabled": True},
    "module_moderation": {"group": "mod", "icon": "⚖️", "name": "Модерация",
                          "description": "Варны, муты, баны, ресты и ЧС.",
                          "default_enabled": True},
    "module_purge": {"group": "purge", "icon": "🧹", "name": "Чистка",
                     "description": "Чистка активности и сводки.",
                     "default_enabled": True},
}

CHAT_MODULE_KEYS: Final = frozenset(CHAT_MODULES)


def _validate_registry() -> None:
    for key, spec in CHAT_MODULES.items():
        if not key.startswith("module_"):
            raise ValueError(f"chat module key must start with module_: {key}")
        if spec["group"] not in CHAT_MODULE_GROUPS:
            raise ValueError(f"unknown group {spec['group']} for {key}")
        for field in ("icon", "name", "description"):
            value = spec.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} needs a non-empty {field}")
        if not isinstance(spec.get("default_enabled"), bool):
            raise ValueError(f"{key} needs boolean default_enabled")
    if MASTER_CHAT_MODULE not in CHAT_MODULES:
        raise ValueError("master chat module must be registered")


_validate_registry()


def chat_module_default(module_key: str) -> bool:
    if module_key not in CHAT_MODULES:
        raise ValueError(f"unknown chat module: {module_key}")
    return bool(CHAT_MODULES[module_key]["default_enabled"])


def chat_modules_in_group(group: str) -> tuple[str, ...]:
    """Ключи группы в порядке реестра (пустой кортеж для неизвестной группы)."""
    return tuple(key for key, spec in CHAT_MODULES.items()
                 if spec["group"] == group)


def is_master_chat_module(module_key: str) -> bool:
    return module_key == MASTER_CHAT_MODULE
