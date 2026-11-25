"""Экраны коллекции хаба питомцев: меню, список, карточка, кормление, бестиарий."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup

from core.miniapp_links import miniapp_url
from core.pets_v1 import MAX_LEVEL
from services.formatting import safe_html

from bot.chat.pets_views import (
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
    route_rows,
)


def _effect_summary(effects: dict) -> str:
    segments = [f"маршрут +{int(effects.get('expedition_route_bonus_percent') or 0)}%"]
    charges = int(effects.get("expedition_hint_charges") or 0)
    if charges:
        segments.append(f"подсказки ×{charges}")
    guard = int(effects.get("expedition_risk_guard_percent") or 0)
    if guard:
        segments.append(f"щит риска {guard}%")
    if effects.get("expedition_extra_option"):
        segments.append("дополнительный вариант (разведка)")
    if effects.get("max_level_effect"):
        segments.append("предел развития")
    return " · ".join(segments)


def menu_view(view: dict, *, user_id: int, pack: Pack) -> tuple[str, InlineKeyboardMarkup]:
    """Хаб питомцев: коллекция, бестиарий, активности или ожидающий маршрут."""
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
        rows.extend(route_rows(pack, user_id, view.get("route_options")))
    if active is not None and food and pet_endurance(active) < 100:
        rows.append([("🍖 Покормить", pack("feed", pet_id=int(active["id"]), user_id=user_id), None)])
    rows.append([("🖼 Открыть в Mini App", None, miniapp_url("pets"))])
    return render_pet_overview(view), markup_rows(rows)


def pets_view(view: dict, *, user_id: int, pack: Pack) -> tuple[str, InlineKeyboardMarkup]:
    """Список коллекции: кнопка на питомца открывает его карточку."""
    pets = list(view.get("pets") or [])
    if not pets:
        text = "🐾 <b>МОИ ПИТОМЦЫ</b>\n\nПитомцев пока нет: первая карточка приходит из сундука."
        return text, menu_button(user_id, pack)
    rows: list[Row] = [
        [(
            f"{pet_icon(pet.get('species_id'))} {safe_html(pet_name(pet))} · {pet_endurance(pet)}/100"
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
    """Питомец подробно: эффекты, активация и вход в кормление."""
    pet = find_pet(view, int(pet_id))
    if pet is None:
        return menu_view(view, user_id=user_id, pack=pack)
    active = bool(pet.get("active"))
    effects = pet.get("effects") or {}
    stage = safe_html(str(effects.get("visual_stage") or "Начальный облик"))
    lines = [
        f"🐾 <b>{pet_icon(pet.get('species_id'))} {safe_html(pet_name(pet))}</b>",
        f"Уровень <b>{pet_level(pet)}</b>/{MAX_LEVEL} · {stage}",
        f"Выносливость: <b>{pet_endurance(pet)}/100</b>",
        "",
        "⭐ <b>Активный спутник</b> — именно он уходит в походы и экспедиции." if active
        else "Не активен. Смена активного стоит −5 выносливости текущего спутника.",
        "",
        f"Экспедиция: {_effect_summary(effects)}.",
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
    """Выбор еды: кнопка на каждый запас, который есть у игрока."""
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
        lines.append("<blockquote>Одна порция восстанавливает выносливость сразу.</blockquote>")
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
    """Виды питомцев: открытые — с иконкой и именем."""
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
    lines += ["", "Карточки питомцев выпадают из сундуков."]
    rows: list[Row] = [
        [("🖼 Открыть в Mini App", None, miniapp_url("pets"))],
        [("🏠 В меню", pack("menu", user_id=user_id), None)],
    ]
    return "\n".join(lines), markup_rows(rows)
