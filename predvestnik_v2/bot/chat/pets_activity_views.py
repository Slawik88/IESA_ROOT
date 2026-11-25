"""Экраны активностей хаба питомцев: старт, общий таймер, маршруты, ускорение."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup

from core.miniapp_links import miniapp_url
from core.pets_v1 import ACTIVITY_ENDURANCE_COST
from services.formatting import safe_html

from bot.chat.pets_views import (
    ACTIVITY_TITLES,
    DEFAULT_DURATIONS,
    Pack,
    Row,
    active_pet,
    activity_sentence,
    key_reward_line,
    markup_rows,
    needs_decision,
    new_token,
    pet_endurance,
    pet_icon,
    pet_name,
    route_meta_lines,
    route_rows,
)


def _reward_note(view: dict, kind: str) -> str:
    note = key_reward_line(view, kind)
    if kind == "expedition" and (view.get("features") or {}).get("route_rewards"):
        note += " Маршрут после таймера: успех приносит мору, неудача ничего не отнимает."
    return note


def activity_view(view: dict, kind: str, *, user_id: int, pack: Pack) -> tuple[str, InlineKeyboardMarkup]:
    """Меню старта похода или экспедиции либо состояние общего таймера."""
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
            for meta in route_meta_lines(view.get("route_options")):
                lines.append(meta)
            rows.extend(route_rows(pack, user_id, view.get("route_options")))
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
            lines.append("<blockquote>Питомцы появляются из карточек в сундуках.</blockquote>")
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
    lines.append(_reward_note(view, kind))
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
    """Экран маршрута: кнопки, только когда экспедиция ждёт выбора."""
    activity = view.get("activity") or None
    rows: list[Row] = []
    if needs_decision(activity):
        lines = [
            "🧭 <b>ВЫБОР МАРШРУТА</b>",
            "",
            "Экспедиция завершена. Выбор окончательный: успех приносит мору, неудача ничего не отнимает.",
        ]
        for meta in route_meta_lines(view.get("route_options")):
            lines.append(meta)
        rows.extend(route_rows(pack, user_id, view.get("route_options")))
        return "\n".join(lines), markup_rows([*rows, [("🏠 В меню", pack("menu", user_id=user_id), None)]])
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
    """Честный ответ на «ускорить поход»: таймеры идут в реальном времени."""
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
            rows.extend(route_rows(pack, user_id, view.get("route_options")))
    else:
        lines.append("Сейчас нет активного похода или экспедиции — можно отправить питомца.")
        rows.append([
            ("🏕 Поход", pack("act", value="trek", user_id=user_id), None),
            ("🧭 Экспедиция", pack("act", value="expedition", user_id=user_id), None),
        ])
    rows.append([("🏠 В меню", pack("menu", user_id=user_id), None)])
    return "\n".join(lines), markup_rows(rows)
