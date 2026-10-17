"""bot/handlers/_chat_module_ui.py — секции «Функции чата» и страницы групп.

Строит тексты и клавиатуры для настроек модулей чата. ChatSettingsCB живёт в
chat_settings.py — сюда он не импортируется, вместо него передаётся фабрика
pack(action, key, value), чтобы не плодить циклический импорт.
"""
from __future__ import annotations

from html import escape
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


def _is_globally_off(module_key: str, global_states: dict | None) -> bool:
    """True = разработчик выключил модуль для всей сети (и он не заработает)."""
    state = (global_states or {}).get(module_key)
    return bool(state) and state.get("enabled", True) is False


def _global_off_note(module_key: str, global_states: dict | None) -> str:
    """Пометка «выключено разработчиком» для строки модуля (иначе пусто)."""
    if not _is_globally_off(module_key, global_states):
        return ""
    reason = (global_states[module_key].get("disabled_reason") or "").strip()
    note = "🌐 выключено глобально"
    if reason:
        note += f": {escape(reason)}"
    return f" · <i>{note}</i>"


def _group_mark(group: str, settings: dict, global_states: dict | None = None) -> tuple[int, int]:
    keys = [k for k, s in CHAT_MODULES.items() if s["group"] == group]
    enabled = sum(
        1 for k in keys
        if module_enabled(settings, k) and not _is_globally_off(k, global_states)
    )
    return enabled, len(keys)


def features_view(
    settings: dict,
    user_id: int,
    pack: PackCB,
    extra_toggles: dict[str, tuple[str, str]],
    global_states: dict | None = None,
) -> tuple[str, types.InlineKeyboardMarkup]:
    """Обзор «🧩 Функции чата»: мастер-стоп, группы и старые тумблеры."""
    total = len(CHAT_MODULES)
    off = total - sum(1 for key in CHAT_MODULES if module_enabled(settings, key))
    master_on = module_enabled(settings, MASTER_CHAT_MODULE)
    global_off = [
        key for key in CHAT_MODULES
        if module_enabled(settings, key) and _is_globally_off(key, global_states)
    ]

    lines = [
        "🧩 <b>ФУНКЦИИ ЧАТА</b>",
        "",
        f"Выключено модулей: <b>{off} из {total}</b>. Каждый пункт отвечает "
        "ровно за одну механику — можно гасить точечно.",
    ]
    if global_off:
        lines.append(
            f"🌐 Разработчик выключил глобально: <b>{len(global_off)}</b> — "
            "включение в этом чате не вернёт их в работу."
        )
    b = InlineKeyboardBuilder()
    b.button(
        text=("✅" if master_on else "❌") + " 🚫 Весь бот в чатах",
        callback_data=pack("toggle", MASTER_CHAT_MODULE, return_context_features(), user_id),
    )
    for group, spec in CHAT_MODULE_GROUPS.items():
        keys = [k for k, s in CHAT_MODULES.items() if s["group"] == group]
        if not keys:
            continue
        enabled, count = _group_mark(group, settings, global_states)
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
    b.button(
        text="♻️ Вернуть стандартные настройки",
        callback_data=pack("reset_confirm", "", "", user_id),
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
    global_states: dict | None = None,
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
        lines.append(
            f"{m['icon']} {m['name']}: <b>{_status(enabled)}</b>"
            f"{_global_off_note(key, global_states)}"
        )
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
