"""Shared primitives for the chat-side pet views (rendering only, no DB I/O).

Every mutating button carries a fresh idempotency token: the service records it
as ``action_id``, so a double tap replays the same durable action instead of
spending food or endurance twice.
"""
from __future__ import annotations

from typing import Callable
from uuid import uuid4

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.chests_v1 import PET_SPECIES
from services.utils import safe_html

Pack = Callable[..., str]
Row = list[tuple[str, str | None, str | None]]

RARITY_LABELS = {
    "common": "обычный",
    "uncommon": "необычный",
    "rare": "редкий",
    "epic": "эпический",
    "legendary": "легендарный",
}
ROUTE_LABELS = {"careful": "осторожный", "steady": "ровный", "bold": "рискованный"}
ACTIVITY_TITLES = {"trek": "🏕 Поход", "expedition": "🧭 Экспедиция"}
DEFAULT_DURATIONS = (3, 6, 9)
_ROUTE_BUTTONS = (
    ("careful", "🛡 Осторожный"),
    ("steady", "⚖️ Ровный"),
    ("bold", "🔥 Рискованный"),
)


class PetsCB(CallbackData, prefix="pv"):
    """One owner-locked pet callback: navigation, or a mutating action with a token."""

    action: str
    pet_id: int = 0
    value: str = ""
    amount: int = 0
    token: str = ""
    user_id: int = 0


def pack_pet_callback(
    action: str,
    *,
    pet_id: int = 0,
    value: str = "",
    amount: int = 0,
    token: str = "",
    user_id: int,
) -> str:
    """Pack one payload; user_id is always part of the ownership contract."""
    return PetsCB(
        action=str(action), pet_id=int(pet_id), value=str(value),
        amount=int(amount), token=str(token), user_id=int(user_id),
    ).pack()


def new_token() -> str:
    """A fresh idempotency token for one rendered button."""
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
    """Standalone «back to hub» button for command confirmations."""
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


def activity_sentence(activity: dict) -> str:
    label = "Поход" if activity.get("kind") == "trek" else "Экспедиция"
    if activity.get("status") == "ready":
        if needs_decision(activity):
            return f"{label}: таймер завершён — выбери маршрут."
        return f"{label}: награда получена, таймер освобождён."
    ends_at = safe_html(str(activity.get("ends_at") or "").replace("T", " ")[:16])
    return f"{label} идёт до <code>{ends_at}</code>."


def route_button_row(pack: Pack, user_id: int) -> Row:
    return [
        (label, pack("route", value=decision, token=new_token(), user_id=user_id), None)
        for decision, label in _ROUTE_BUTTONS
    ]


def render_pet_overview(view: dict) -> str:
    """Render the owner's pet snapshot as the hub text (buttons are added on top)."""
    pets = list(view.get("pets") or [])
    activity = view.get("activity")
    activity_line = ""
    if activity:
        label = "Поход" if activity.get("kind") == "trek" else "Экспедиция"
        if activity.get("status") == "ready":
            if activity.get("kind") == "expedition" and not activity.get("decision"):
                activity_line = (
                    f"\n\n⏳ <b>{label}: таймер завершён.</b> Выбери маршрут: "
                    "<code>бот маршрут, осторожный</code>, <code>ровный</code> или <code>рискованный</code>."
                )
            elif activity.get("decision"):
                route = ROUTE_LABELS.get(str(activity["decision"]), "новый")
                activity_line = (
                    f"\n\n✅ <b>{label}: выбран {route} маршрут.</b> Ключ уже зачислен."
                )
            else:
                activity_line = f"\n\n✅ <b>{label}: таймер завершён.</b> Ключ уже зачислен."
        else:
            ends_at = safe_html(str(activity.get("ends_at") or "").replace("T", " ")[:16])
            activity_line = f"\n\n⏳ <b>{label} идёт.</b> Завершение: <code>{ends_at}</code>."
    if not pets:
        return (
            "🐾 <b>ПИТОМЦЫ</b>\n\n"
            "У тебя пока нет питомцев. Когда питомец появится в коллекции, здесь будет его уровень и выносливость.\n\n"
            "Первого питомца можно открыть карточкой из сундука. Походы и экспедиции дают по одному ключу."
            + activity_line
        )
    lines = ["🐾 <b>ПИТОМЦЫ</b>", ""]
    for pet in pets:
        active = " · активный ⭐" if pet.get("active") else ""
        effects = pet.get("effects") or {}
        stage = safe_html(str(effects.get("visual_stage") or "Начальный облик"))
        lines.append(
            f"• {pet_icon(pet.get('species_id'))} <b>{safe_html(pet_name(pet))}</b> · ур. {pet_level(pet)}"
            f" · <b>{pet_endurance(pet)}/100</b>{active} · {stage}"
        )
    lines.extend([
        "",
        "Выносливость тратится на походы и смену активного, еда из сундуков восстанавливает её сразу.",
        "За завершённый поход или экспедицию выдаётся один ключ.",
    ])
    return "\n".join(lines) + activity_line
