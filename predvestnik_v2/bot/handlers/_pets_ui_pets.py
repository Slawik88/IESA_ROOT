"""Collection views for the chat pet hub: hub menu, list, card, feeding, bestiary."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup

from bot.handlers._pets_ui_base import (
    Pack,
    RARITY_LABELS,
    Row,
    active_pet,
    find_pet,
    markup_rows,
    menu_button,
    needs_decision,
    new_token,
    pet_endurance,
    pet_icon,
    pet_level,
    pet_name,
    render_pet_overview,
    route_button_row,
)
from core.miniapp_links import miniapp_url
from services.utils import safe_html


def _effect_summary(effects: dict) -> str:
    segments = [f"маршрут +{int(effects.get('expedition_route_bonus_percent') or 0)}%"]
    charges = int(effects.get("expedition_hint_charges") or 0)
    if charges:
        segments.append(f"подсказки ×{charges}")
    guard = int(effects.get("expedition_risk_guard_percent") or 0)
    if guard:
        segments.append(f"щит риска {guard}%")
    if effects.get("expedition_extra_option"):
        segments.append("дополнительный вариант")
    if effects.get("max_level_effect"):
        segments.append("предел развития")
    return " · ".join(segments)


def menu_view(view: dict, *, user_id: int, pack: Pack) -> tuple[str, InlineKeyboardMarkup]:
    """Pet hub: collection, bestiary, activities (or the pending route choice)."""
    pets = list(view.get("pets") or [])
    activity = view.get("activity") or None
    active = active_pet(view)
    food = list(view.get("food") or [])
    owned = int(view.get("bestiary_owned") or 0)
    total = int(view.get("bestiary_total") or 0)
    rows: list[Row] = []
    top: Row = []
    if pets:
        top.append((f"🐾 Мои питомцы · {len(pets)}", pack("pets", user_id=user_id), None))
    if total:
        top.append((f"📖 Бестиарий · {owned}/{total}", pack("best", user_id=user_id), None))
    if top:
        rows.append(top)
    if activity is None:
        rows.append([
            ("🏕 Поход", pack("act", value="trek", user_id=user_id), None),
            ("🧭 Экспедиция", pack("act", value="expedition", user_id=user_id), None),
        ])
    elif needs_decision(activity):
        rows.append(route_button_row(pack, user_id))
    if active is not None and food and pet_endurance(active) < 100:
        rows.append([("🍖 Покормить", pack("feed", pet_id=int(active["id"]), user_id=user_id), None)])
    rows.append([("🖼 Открыть в Mini App", None, miniapp_url("pets"))])
    return render_pet_overview(view), markup_rows(rows)


def pets_view(view: dict, *, user_id: int, pack: Pack) -> tuple[str, InlineKeyboardMarkup]:
    """Collection list: one button per pet opens its card."""
    pets = list(view.get("pets") or [])
    if not pets:
        text = "🐾 <b>МОИ ПИТОМЦЫ</b>\n\nПитомцев пока нет: первая карточка появляется из сундука."
        return text, menu_button(user_id, pack)
    rows: list[Row] = [
        [(
            f"{pet_icon(pet.get('species_id'))} {pet_name(pet)} · {pet_endurance(pet)}/100"
            f"{' ⭐' if pet.get('active') else ''}",
            pack("pet", pet_id=int(pet["id"]), user_id=user_id),
            None,
        )]
        for pet in pets
    ]
    rows.append([("🏠 В меню", pack("menu", user_id=user_id), None)])
    text = f"🐾 <b>МОИ ПИТОМЦЫ</b> · {len(pets)}\n\nВыбери питомца: карточка, кормление, смена активного."
    return text, markup_rows(rows)


def pet_card_view(view: dict, pet_id: int, *, user_id: int, pack: Pack) -> tuple[str, InlineKeyboardMarkup]:
    """One pet in detail: effects, activation and feeding entry points."""
    pet = find_pet(view, int(pet_id))
    if pet is None:
        return menu_view(view, user_id=user_id, pack=pack)
    active = bool(pet.get("active"))
    effects = pet.get("effects") or {}
    stage = safe_html(str(effects.get("visual_stage") or "Начальный облик"))
    lines = [
        f"🐾 <b>{pet_icon(pet.get('species_id'))} {safe_html(pet_name(pet))}</b>",
        f"Уровень <b>{pet_level(pet)}</b>/16 · {stage}",
        f"Выносливость: <b>{pet_endurance(pet)}/100</b>",
        "",
        "⭐ <b>Активный спутник</b> — именно он уходит в походы." if active
        else "Не активен. Смена активного стоит −5 выносливости текущего спутника.",
        "",
        "Экспедиция: " + _effect_summary(effects),
    ]
    rows: list[Row] = []
    if not active:
        rows.append([(
            "⭐ Сделать активным",
            pack("activate", pet_id=int(pet["id"]), token=new_token(), user_id=user_id),
            None,
        )])
    if view.get("food") and pet_endurance(pet) < 100:
        rows.append([("🍖 Покормить", pack("feed", pet_id=int(pet["id"]), user_id=user_id), None)])
    rows.append([
        ("⬅️ К питомцам", pack("pets", user_id=user_id), None),
        ("🏠 В меню", pack("menu", user_id=user_id), None),
    ])
    return "\n".join(lines), markup_rows(rows)


def feed_view(view: dict, pet_id: int, *, user_id: int, pack: Pack) -> tuple[str, InlineKeyboardMarkup]:
    """Food chooser: one button per food stack the owner holds."""
    pet = find_pet(view, int(pet_id))
    if pet is None:
        return menu_view(view, user_id=user_id, pack=pack)
    food = list(view.get("food") or [])
    lines = [
        f"🍖 <b>КОРМЛЕНИЕ · {pet_icon(pet.get('species_id'))} {safe_html(pet_name(pet))}</b>",
        f"Выносливость: <b>{pet_endurance(pet)}/100</b>",
        "",
    ]
    rows: list[Row] = []
    if pet_endurance(pet) >= 100:
        lines.append("Выносливость уже полная — кормление подождёт.")
    elif not food:
        lines.append("Еды нет: она выпадает из сундуков.")
        rows.append([("🖼 Открыть в Mini App", None, miniapp_url("pets"))])
    else:
        lines.append("Выбери еду: одна порция восстанавливает выносливость сразу.")
        rows.extend([
            [(
                f"{item.get('icon') or '🍖'} {item.get('name') or 'Еда'}"
                f" +{int(item.get('restore') or 0)} · ×{int(item.get('quantity') or 0)}",
                pack(
                    "food", pet_id=int(pet["id"]), value=str(item.get("id") or ""),
                    token=new_token(), user_id=user_id,
                ),
                None,
            )]
            for item in food
        ])
    rows.append([
        ("⬅️ К карточке", pack("pet", pet_id=int(pet["id"]), user_id=user_id), None),
        ("🏠 В меню", pack("menu", user_id=user_id), None),
    ])
    return "\n".join(lines), markup_rows(rows)


def bestiary_view(view: dict, *, user_id: int, pack: Pack) -> tuple[str, InlineKeyboardMarkup]:
    """Collection of species: owned entries open with icon and name."""
    species_rows = list(view.get("bestiary") or [])
    owned = int(view.get("bestiary_owned") or 0)
    total = int(view.get("bestiary_total") or len(species_rows))
    lines = [f"📖 <b>БЕСТИАРИЙ</b> · {owned}/{total}", ""]
    for species in species_rows:
        rarity = RARITY_LABELS.get(str(species.get("rarity") or ""), str(species.get("rarity") or "вид"))
        if species.get("owned"):
            icon = str(species.get("icon") or "🐾")
            lines.append(f"{icon} <b>{safe_html(str(species.get('name') or 'Питомец'))}</b> · {rarity} · открыт ✅")
        else:
            lines.append(f"❔ <b>Неизвестный питомец</b> · {rarity} · не найден")
    lines.extend(["", "Карточки питомцев выпадают из сундуков."])
    rows: list[Row] = [
        [("🖼 Открыть в Mini App", None, miniapp_url("pets"))],
        [("🏠 В меню", pack("menu", user_id=user_id), None)],
    ]
    return "\n".join(lines), markup_rows(rows)
