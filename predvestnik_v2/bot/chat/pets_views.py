"""Кнопочные экраны хаба питомцев: общие примитивы и текст хаба.

Только рендер — запросов к базе здесь нет. У каждой меняющей кнопки свежий
токен идемпотентности: сервис записывает его как ``action_id``, поэтому
двойной тап повторяет тот же результат, а не списывает еду или выносливость
дважды.
"""
from __future__ import annotations

from typing import Callable
from uuid import uuid4

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.chests_v1 import PET_SPECIES
from services.formatting import safe_html

Pack = Callable[..., str]
Row = list[tuple[str, str | None, str | None]]

RARITY_LABELS = {
    "common": "обычный",
    "uncommon": "необычный",
    "rare": "редкий",
    "epic": "эпический",
    "legendary": "легендарный",
}
ROUTE_LABELS = {"careful": "осторожный", "steady": "ровный", "scout": "разведка", "bold": "рискованный"}
ROUTE_BUTTONS = (
    ("careful", "🛡 Осторожный"),
    ("steady", "⚖️ Ровный"),
    ("scout", "🔍 Разведка"),
    ("bold", "🔥 Рискованный"),
)
CLASSIC_ROUTES = ("careful", "steady", "bold")
ACTIVITY_TITLES = {"trek": "🏕 Поход", "expedition": "🧭 Экспедиция"}
DEFAULT_DURATIONS = (3, 6, 9)


class PetsCB(CallbackData, prefix="pv"):
    """Кнопка питомцев: навигация или действие со свежим токеном."""

    action: str
    pet_id: int = 0
    value: str = ""
    amount: int = 0
    token: str = ""
    user_id: int = 0


def pack_pet_callback(action: str, *, pet_id: int = 0, value: str = "", amount: int = 0,
                      token: str = "", user_id: int) -> str:
    """Собрать один callback: владелец всегда часть контракта."""
    return PetsCB(
        action=str(action), pet_id=int(pet_id), value=str(value),
        amount=int(amount), token=str(token), user_id=int(user_id),
    ).pack()


def new_token() -> str:
    """Свежий токен идемпотентности для одной отрисованной кнопки."""
    return uuid4().hex[:12]


def _button(text: str, callback_data: str | None, url: str | None) -> InlineKeyboardButton:
    if url:
        return InlineKeyboardButton(text=text, url=url)
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def markup_rows(rows: list[Row]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for row in rows:
        builder.row(*(_button(text, data, url) for text, data, url in row))
    return builder.as_markup()


def menu_button(user_id: int, pack: Pack = pack_pet_callback) -> InlineKeyboardMarkup:
    """Одна кнопка «в меню» для подтверждений команд."""
    return markup_rows([[("🏠 В меню", pack("menu", user_id=int(user_id)), None)]])


def pet_icon(species_id) -> str:
    row = PET_SPECIES.get(str(species_id or ""))
    return str(row["icon"]) if row else "🐾"


def pet_name(pet: dict) -> str:
    return str(pet.get("name") or "Питомец")


def pet_level(pet: dict) -> int:
    try:
        return max(1, int(pet.get("level") or 1))
    except (TypeError, ValueError):
        return 1


def pet_endurance(pet: dict) -> int:
    try:
        return max(0, min(100, int(pet.get("endurance"))))
    except (TypeError, ValueError):
        return 0


def find_pet(view: dict, pet_id: int) -> dict | None:
    for pet in view.get("pets") or []:
        if int(pet.get("id") or 0) == int(pet_id):
            return pet
    return None


def active_pet(view: dict) -> dict | None:
    for pet in view.get("pets") or []:
        if pet.get("active"):
            return pet
    return None


def needs_decision(activity: dict | None) -> bool:
    return bool(activity) and (
        activity.get("status") == "ready"
        and activity.get("kind") == "expedition"
        and not activity.get("decision")
    )


def format_ends_at(value) -> str:
    return safe_html(str(value or "").replace("T", " ")[:16])


def keys_word(count: int) -> str:
    count = abs(int(count))
    if count % 10 == 1 and count % 100 != 11:
        return "ключ"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return "ключа"
    return "ключей"


def key_reward_line(view: dict, kind: str) -> str:
    """Сколько ключей даёт завершение: поход — 1, экспедиция — 2."""
    counts = view.get("activity_key_counts") or {}
    keys = int(counts.get(kind) or (2 if str(kind) == "expedition" else 1))
    return f"За завершение — <b>{keys} {keys_word(keys)}</b>."


def activity_sentence(activity: dict) -> str:
    """Одна строка о состоянии общего таймера."""
    label = "Поход" if activity.get("kind") == "trek" else "Экспедиция"
    if activity.get("status") == "ready":
        if needs_decision(activity):
            return f"{label}: таймер завершён — выбери маршрут."
        if activity.get("decision"):
            route = ROUTE_LABELS.get(str(activity["decision"]), "выбранный")
            return f"{label}: маршрут «{route}» выбран, итог записан."
        return f"{label}: награда получена, таймер освобождён."
    return f"{label} идёт до <code>{format_ends_at(activity.get('ends_at'))}</code>."


def route_meta_lines(route_options: dict | None) -> list[str]:
    """Строки-подсказки под кнопками маршрутов: шансы с 4 уровня и недельный лимит моры."""
    if not route_options or not route_options.get("rewards_enabled"):
        return []
    lines: list[str] = []
    if not route_options.get("hint"):
        lines.append("<i>С 4 уровня питомец покажет шансы маршрутов.</i>")
    remaining, cap = route_options.get("weekly_remaining_mora"), route_options.get("weekly_cap_mora")
    if remaining is not None and cap is not None:
        lines.append(f"<i>Награды маршрутов на этой неделе: осталось {int(remaining)} из {int(cap)} 🪙.</i>")
    return lines


def route_rows(pack: Pack, user_id: int, route_options: dict | None = None) -> list[Row]:
    """Кнопки маршрутов завершённой экспедиции.

    С включёнными наградами берём живой список сервиса (разведка открывается
    с 12 уровня, шансы и мора — когда питомец дорос до подсказок), иначе —
    три классических маршрута.
    """
    entries: list[tuple[str, str]] = []
    if route_options and route_options.get("rewards_enabled") and route_options.get("routes"):
        labels = dict(ROUTE_BUTTONS)
        for item in route_options["routes"]:
            route = str(item.get("id") or "")
            if route not in labels:
                continue
            label = labels[route]
            if item.get("chance_percent") is not None:
                label += f" · {int(item['chance_percent'])}% · +{int(item.get('reward_mora') or 0)} 🪙"
            entries.append((route, label))
    if not entries:
        entries = [(route, dict(ROUTE_BUTTONS)[route]) for route in CLASSIC_ROUTES]
    step = 2 if len(entries) > 3 or any("%" in label for _, label in entries) else len(entries)
    return [
        [(label, pack("route", value=route, token=new_token(), user_id=user_id), None)
         for route, label in entries[index:index + step]]
        for index in range(0, len(entries), step)
    ]


def _activity_line(activity: dict, route_options: dict | None) -> str:
    label = "Поход" if activity.get("kind") == "trek" else "Экспедиция"
    if activity.get("status") != "ready":
        return f"⏳ <b>{label} идёт.</b> Завершение: <code>{format_ends_at(activity.get('ends_at'))}</code>."
    if needs_decision(activity):
        line = (f"⏳ <b>{label}: таймер завершён — нужен маршрут.</b> "
                "Выбери кнопкой ниже или командой <code>бот маршрут, осторожный</code>.")
        for meta in route_meta_lines(route_options):
            line += f"\n{meta}"
        return line
    if activity.get("decision"):
        route = ROUTE_LABELS.get(str(activity["decision"]), "выбранный")
        return f"✅ <b>{label}: маршрут «{route}» — итог записан.</b>"
    return f"✅ <b>{label}: таймер завершён, награда зачислена.</b>"


def render_pet_overview(view: dict) -> str:
    """Снимок коллекции и активности — текст открытия хаба."""
    pets = list(view.get("pets") or [])
    lines: list[str]
    if not pets:
        lines = [
            "🐾 <b>ПИТОМЦЫ</b>",
            "",
            "У тебя пока нет питомцев: первая карточка приходит из сундука. "
            "Походы и экспедиции приносят ключи — 1 и 2 соответственно.",
        ]
    else:
        lines = ["🐾 <b>ПИТОМЦЫ</b>", ""]
        for pet in pets:
            active = " · активный ⭐" if pet.get("active") else ""
            effects = pet.get("effects") or {}
            stage = safe_html(str(effects.get("visual_stage") or "Начальный облик"))
            lines.append(
                f"• {pet_icon(pet.get('species_id'))} <b>{safe_html(pet_name(pet))}</b> · ур. {pet_level(pet)}"
                f" · выносливость <b>{pet_endurance(pet)}/100</b>{active} · {stage}"
            )
        lines += [
            "",
            "<blockquote>Выносливость тратит активный спутник: походы, экспедиции и смена активного. "
            "Еда из сундуков восстанавливает её сразу.\n"
            "Ключи: 1 за поход, 2 за экспедицию.</blockquote>",
        ]
    activity = view.get("activity") or None
    if activity:
        lines += ["", _activity_line(activity, view.get("route_options"))]
    return "\n".join(lines)
