"""bot/handlers/_chat_module_ui.py — секции «Функции чата» и страницы групп.

Строит тексты и клавиатуры для настроек модулей чата. ChatSettingsCB живёт в
chat_settings.py — сюда он не импортируется, вместо него передаётся фабрика
pack(action, key, value), чтобы не плодить циклический импорт.
"""
from __future__ import annotations

from typing import Callable

from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.chat_modules import (
    CHAT_MODULES,
    CHAT_MODULE_GROUPS,
    MASTER_CHAT_MODULE,
)

PackCB = Callable[..., str]


def return_context_features() -> str:
    return "features"


def return_context_group(group: str) -> str:
    return f"grp:{group}"


def module_enabled(settings: dict, module_key: str) -> bool:
    spec = CHAT_MODULES.get(module_key, {})
    default = int(bool(spec.get("default_enabled", True)))
    return bool(settings.get(module_key, default))


def _status(enabled: bool) -> str:
    return "включено" if enabled else "выключено"


def _group_mark(group: str, settings: dict) -> tuple[int, int]:
    keys = [k for k, s in CHAT_MODULES.items() if s["group"] == group]
    enabled = sum(1 for k in keys if module_enabled(settings, k))
    return enabled, len(keys)


def features_view(
    settings: dict,
    user_id: int,
    pack: PackCB,
    extra_toggles: dict[str, tuple[str, str]],
) -> tuple[str, types.InlineKeyboardMarkup]:
    """Обзор «🧩 Функции чата»: мастер-стоп, группы и старые тумблеры."""
    total = len(CHAT_MODULES)
    off = total - sum(1 for key in CHAT_MODULES if module_enabled(settings, key))
    master_on = module_enabled(settings, MASTER_CHAT_MODULE)

    lines = [
        "🧩 <b>ФУНКЦИИ ЧАТА</b>",
        "",
        f"Выключено модулей: <b>{off} из {total}</b>. Каждый пункт отвечает "
        "ровно за одну механику — можно гасить точечно.",
    ]
    b = InlineKeyboardBuilder()
    b.button(
        text=("✅" if master_on else "❌") + " 🚫 Весь бот в чатах",
        callback_data=pack("toggle", MASTER_CHAT_MODULE, return_context_features(), user_id),
    )
    for group, spec in CHAT_MODULE_GROUPS.items():
        keys = [k for k, s in CHAT_MODULES.items() if s["group"] == group]
        if not keys:
            continue
        enabled, count = _group_mark(group, settings)
        lines.append(f"{spec['icon']} {spec['name']}: <b>{enabled}/{count}</b>")
        b.button(
            text=f"{spec['icon']} {spec['name']} · {enabled}/{count}",
            callback_data=pack("fgroup", group, "", user_id),
        )
    for key, (icon, desc) in extra_toggles.items():
        enabled = bool(settings.get(key, 1))
        b.button(
            text=f"{'✅' if enabled else '❌'} {icon} {desc}",
            callback_data=pack("toggle", key, return_context_features(), user_id),
        )
    b.button(text="⬅️ Все настройки", callback_data=pack("menu", "", "", user_id))
    b.adjust(1)
    return "\n".join(lines), b.as_markup()


def group_view(
    settings: dict,
    group: str,
    user_id: int,
    pack: PackCB,
    extra_toggles: dict[str, tuple[str, str]] | None = None,
) -> tuple[str, types.InlineKeyboardMarkup] | None:
    """Страница группы: точечные переключатели модулей одной категории."""
    spec = CHAT_MODULE_GROUPS.get(group)
    if not spec:
        return None
    keys = tuple(k for k, s in CHAT_MODULES.items() if s["group"] == group)
    # Legacy-тумблеры живут в группе «core» рядом с мастер-стопом.
    extra = extra_toggles or {}
    extra_keys = tuple(extra) if group == "core" else ()

    lines = [f"{spec['icon']} <b>{spec['name'].upper()}</b>", ""]
    b = InlineKeyboardBuilder()
    for key in keys:
        m = CHAT_MODULES[key]
        enabled = module_enabled(settings, key)
        lines.append(f"{m['icon']} {m['name']}: <b>{_status(enabled)}</b>")
        b.button(
            text=f"{'✅' if enabled else '❌'} {m['icon']} {m['name']}",
            callback_data=pack("toggle", key, return_context_group(group), user_id),
        )
    for key in extra_keys:
        icon, desc = extra[key]
        enabled = bool(settings.get(key, 1))
        lines.append(f"{icon} {desc}: <b>{_status(enabled)}</b>")
        b.button(
            text=f"{'✅' if enabled else '❌'} {icon} {desc}",
            callback_data=pack("toggle", key, return_context_group(group), user_id),
        )
    b.button(text="⬅️ Функции", callback_data=pack("section", "features", "", user_id))
    b.adjust(1)
    return "\n".join(lines), b.as_markup()
