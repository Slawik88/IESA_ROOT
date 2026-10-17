"""Activity views for the chat pet hub: start chooser, shared timer, routes."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup

from bot.handlers._pets_ui_base import (
    ACTIVITY_TITLES,
    DEFAULT_DURATIONS,
    Pack,
    Row,
    active_pet,
    activity_sentence,
    markup_rows,
    needs_decision,
    new_token,
    pet_endurance,
    pet_icon,
    pet_name,
    route_button_row,
)
from core.miniapp_links import miniapp_url
from core.pets_v1 import ACTIVITY_ENDURANCE_COST
from services.utils import safe_html


def activity_view(view: dict, kind: str, *, user_id: int, pack: Pack) -> tuple[str, InlineKeyboardMarkup]:
    """Start menu for a trek or expedition, or the status of the shared timer."""
    kind = "expedition" if str(kind) == "expedition" else "trek"
    activity = view.get("activity") or None
    rows: list[Row] = []
    if activity is not None:
        running = ACTIVITY_TITLES.get(str(activity.get("kind"))) or ACTIVITY_TITLES[kind]
        lines = [
            running,
            "",
            activity_sentence(activity),
            "",
            "Один общий таймер: следующий запуск — только после финиша.",
        ]
        if needs_decision(activity):
            lines.append("Выбери маршрут кнопками ниже.")
            rows.append(route_button_row(pack, user_id))
        rows.append([("🏠 В меню", pack("menu", user_id=user_id), None)])
        return "\n".join(lines), markup_rows(rows)
    active = active_pet(view)
    if active is None:
        lines = [
            ACTIVITY_TITLES[kind],
            "",
            "Сначала выбери активного питомца — в таймер отправляется именно он.",
        ]
        if view.get("pets"):
            rows.append([("🐾 Выбрать питомца", pack("pets", user_id=user_id), None)])
        else:
            lines.append("Питомцы появляются из карточек в сундуках.")
            rows.append([("🖼 Открыть в Mini App", None, miniapp_url("pets"))])
        rows.append([("🏠 В меню", pack("menu", user_id=user_id), None)])
        return "\n".join(lines), markup_rows(rows)
    endurance = pet_endurance(active)
    costs = view.get("activity_costs") or ACTIVITY_ENDURANCE_COST
    durations = [int(hours) for hours in (view.get("durations") or DEFAULT_DURATIONS)]
    lines = [
        ACTIVITY_TITLES[kind],
        "",
        f"Активный: {pet_icon(active.get('species_id'))} <b>{safe_html(pet_name(active))}</b>"
        f" · выносливость <b>{endurance}/100</b>",
        "",
        "Выбери длительность — выносливость списывается при старте:",
    ]
    if kind == "expedition":
        lines.append("После таймера выберешь маршрут.")
    lines.append("За завершение — 1 ключ.")
    rows.append([
        (
            f"{hours} ч · −{int(costs.get(hours) or 0)}",
            pack("start", value=kind, amount=hours, token=new_token(), user_id=user_id),
            None,
        )
        for hours in durations
    ])
    if durations and endurance < min(int(costs.get(hours) or 0) for hours in durations):
        lines.extend(["", "⚠️ Выносливости не хватает — сначала покорми питомца."])
        if view.get("food"):
            rows.append([("🍖 Покормить", pack("feed", pet_id=int(active["id"]), user_id=user_id), None)])
    rows.append([("🏠 В меню", pack("menu", user_id=user_id), None)])
    return "\n".join(lines), markup_rows(rows)


def route_view(view: dict, *, user_id: int, pack: Pack) -> tuple[str, InlineKeyboardMarkup]:
    """Explicit route screen: buttons only when an expedition waits for one."""
    activity = view.get("activity") or None
    rows: list[Row] = []
    if needs_decision(activity):
        text = (
            "🧭 <b>ВЫБОР МАРШРУТА</b>\n\n"
            "Экспедиция завершена. Маршрут записывается в журнал итогов, выбор окончательный."
        )
        rows.append(route_button_row(pack, user_id))
    else:
        if activity is not None and activity.get("kind") == "expedition":
            reason = "Экспедиция ещё идёт — маршрут выбирается после завершения таймера."
        elif activity is not None:
            reason = "Сейчас идёт поход: маршрут выбирается только у экспедиции."
        else:
            reason = "Нет завершённой экспедиции: сначала запусти её из хаба."
            rows.append([
                ("🏕 Поход", pack("act", value="trek", user_id=user_id), None),
                ("🧭 Экспедиция", pack("act", value="expedition", user_id=user_id), None),
            ])
        text = f"🧭 <b>МАРШРУТ</b>\n\n{reason}"
    rows.append([("🏠 В меню", pack("menu", user_id=user_id), None)])
    return text, markup_rows(rows)


def speedup_view(view: dict, *, user_id: int, pack: Pack) -> tuple[str, InlineKeyboardMarkup]:
    """Honest answer to «ускорить поход»: timers run in real time."""
    activity = view.get("activity") or None
    lines = ["⏳ <b>УСКОРЕНИЕ ПОХОДА</b>", ""]
    rows: list[Row] = []
    if activity is not None and activity.get("status") == "active":
        lines.append("Ускорения нет: таймер идёт в реальном времени, выносливость уже списана.")
        lines.append(activity_sentence(activity))
    elif activity is not None:
        lines.append("Ускорение не нужно — таймер уже завершён.")
        lines.append(activity_sentence(activity))
        if needs_decision(activity):
            lines.append("Выбери маршрут кнопками ниже.")
            rows.append(route_button_row(pack, user_id))
    else:
        lines.append("Сейчас нет активного похода или экспедиции — можно отправить питомца.")
        rows.append([
            ("🏕 Поход", pack("act", value="trek", user_id=user_id), None),
            ("🧭 Экспедиция", pack("act", value="expedition", user_id=user_id), None),
        ])
    rows.append([("🏠 В меню", pack("menu", user_id=user_id), None)])
    return "\n".join(lines), markup_rows(rows)
