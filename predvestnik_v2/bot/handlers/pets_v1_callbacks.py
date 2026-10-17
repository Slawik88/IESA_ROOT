"""Owner-locked callback handlers for the chat-side pet hub.

Every navigation tap re-renders the message for the callback owner only, and
every mutating tap replays its durable ``action_id`` (the per-render token), so
a double tap cannot spend food or endurance twice.
"""
from __future__ import annotations

import re

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest

from bot.handlers import _pets_ui as ui
from bot.middlewares.module_check_mw import ModuleCheckMiddleware
from core.chests_v1 import FOODS
from services import pets_v1
from services.utils import check_callback_owner

router = Router(name="pets_v1_callbacks")
router.callback_query.middleware(ModuleCheckMiddleware("module_pets"))

_TOKEN_RE = re.compile(r"^[0-9a-f]{12}$")


async def _guard(query: types.CallbackQuery, callback_data: ui.PetsCB) -> bool:
    return await check_callback_owner(query, int(callback_data.user_id))


async def _edit(query: types.CallbackQuery, text: str, markup) -> None:
    try:
        await query.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).lower():
            raise


def _action_id(kind: str, token: str) -> str:
    value = str(token or "")
    if not _TOKEN_RE.fullmatch(value):
        raise pets_v1.PetPolicyError("Кнопка устарела — открой питомцев заново.")
    return f"chat:{kind}:{value}"


async def _menu(query: types.CallbackQuery, db, user_id: int) -> None:
    view = await pets_v1.chat_overview(db, user_id)
    text, markup = ui.menu_view(view, user_id=user_id, pack=ui.pack_pet_callback)
    await _edit(query, text, markup)


async def _fail(query: types.CallbackQuery, db, user_id: int, error: Exception) -> None:
    await query.answer(f"❌ {error}", show_alert=True)
    await _menu(query, db, user_id)


@router.callback_query(ui.PetsCB.filter(F.action == "menu"))
async def cb_pet_menu(query: types.CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(query, callback_data):
        return
    user_id = int(callback_data.user_id)
    await query.answer()
    await _menu(query, db, user_id)


@router.callback_query(ui.PetsCB.filter(F.action == "pets"))
async def cb_pet_list(query: types.CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(query, callback_data):
        return
    user_id = int(callback_data.user_id)
    await query.answer()
    view = await pets_v1.chat_overview(db, user_id)
    text, markup = ui.pets_view(view, user_id=user_id, pack=ui.pack_pet_callback)
    await _edit(query, text, markup)


@router.callback_query(ui.PetsCB.filter(F.action == "pet"))
async def cb_pet_card(query: types.CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(query, callback_data):
        return
    user_id = int(callback_data.user_id)
    await query.answer()
    view = await pets_v1.chat_overview(db, user_id)
    text, markup = ui.pet_card_view(
        view, int(callback_data.pet_id), user_id=user_id, pack=ui.pack_pet_callback,
    )
    await _edit(query, text, markup)


@router.callback_query(ui.PetsCB.filter(F.action == "best"))
async def cb_pet_bestiary(query: types.CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(query, callback_data):
        return
    user_id = int(callback_data.user_id)
    await query.answer()
    view = await pets_v1.chat_overview(db, user_id)
    text, markup = ui.bestiary_view(view, user_id=user_id, pack=ui.pack_pet_callback)
    await _edit(query, text, markup)


@router.callback_query(ui.PetsCB.filter(F.action == "act"))
async def cb_pet_activity_chooser(query: types.CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(query, callback_data):
        return
    user_id = int(callback_data.user_id)
    kind = str(callback_data.value) if str(callback_data.value) in ui.ACTIVITY_TITLES else "trek"
    await query.answer()
    view = await pets_v1.chat_overview(db, user_id)
    text, markup = ui.activity_view(view, kind, user_id=user_id, pack=ui.pack_pet_callback)
    await _edit(query, text, markup)


@router.callback_query(ui.PetsCB.filter(F.action == "feed"))
async def cb_pet_feed_chooser(query: types.CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(query, callback_data):
        return
    user_id = int(callback_data.user_id)
    await query.answer()
    view = await pets_v1.chat_overview(db, user_id)
    text, markup = ui.feed_view(
        view, int(callback_data.pet_id), user_id=user_id, pack=ui.pack_pet_callback,
    )
    await _edit(query, text, markup)


@router.callback_query(ui.PetsCB.filter(F.action == "activate"))
async def cb_pet_activate(query: types.CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(query, callback_data):
        return
    user_id, pet_id = int(callback_data.user_id), int(callback_data.pet_id)
    try:
        await pets_v1.select_active_pet(db, user_id, pet_id, _action_id("active", callback_data.token))
    except pets_v1.PetPolicyError as error:
        await _fail(query, db, user_id, error)
        return
    view = await pets_v1.chat_overview(db, user_id)
    pet = ui.find_pet(view, pet_id)
    await query.answer(f"⭐ {_pet_label(pet)} — теперь активный спутник.")
    text, markup = ui.pet_card_view(view, pet_id, user_id=user_id, pack=ui.pack_pet_callback)
    await _edit(query, text, markup)


@router.callback_query(ui.PetsCB.filter(F.action == "food"))
async def cb_pet_feed(query: types.CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(query, callback_data):
        return
    user_id, pet_id = int(callback_data.user_id), int(callback_data.pet_id)
    food_id = str(callback_data.value)
    try:
        result = await pets_v1.feed_pet(
            db, user_id=user_id, pet_id=pet_id, food_id=food_id,
            action_id=_action_id("feed", callback_data.token),
        )
    except pets_v1.PetPolicyError as error:
        await _fail(query, db, user_id, error)
        return
    food = FOODS.get(food_id) or {}
    await query.answer(
        f"{food.get('icon') or '🍖'} +{int(food.get('restore') or 0)} → "
        f"{int(result.get('endurance') or 0)}/100 · осталось {int(result.get('remaining') or 0)} шт."
    )
    view = await pets_v1.chat_overview(db, user_id)
    text, markup = ui.pet_card_view(view, pet_id, user_id=user_id, pack=ui.pack_pet_callback)
    await _edit(query, text, markup)


@router.callback_query(ui.PetsCB.filter(F.action == "start"))
async def cb_pet_start(query: types.CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(query, callback_data):
        return
    user_id = int(callback_data.user_id)
    kind = str(callback_data.value) if str(callback_data.value) in ui.ACTIVITY_TITLES else "trek"
    hours = int(callback_data.amount)
    try:
        result = await pets_v1.start_activity(
            db, user_id=user_id, kind=kind, hours=hours,
            action_id=_action_id("start", callback_data.token),
        )
    except pets_v1.PetPolicyError as error:
        await _fail(query, db, user_id, error)
        return
    activity = result.get("activity") or {}
    ends_at = str(activity.get("ends_at") or "").replace("T", " ")[:16]
    title = "Поход" if kind == "trek" else "Экспедиция"
    await query.answer(
        f"{ui.ACTIVITY_TITLES[kind]} · {hours} ч запущен · финиш {ends_at}"
        f" · ⚡ {int(result.get('endurance') or 0)}/100"
    )
    await _menu(query, db, user_id)


@router.callback_query(ui.PetsCB.filter(F.action == "route"))
async def cb_pet_route(query: types.CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(query, callback_data):
        return
    user_id = int(callback_data.user_id)
    decision = str(callback_data.value)
    try:
        result = await pets_v1.choose_expedition(
            db, user_id=user_id, decision=decision,
            action_id=_action_id("route", callback_data.token),
        )
    except pets_v1.PetPolicyError as error:
        await _fail(query, db, user_id, error)
        return
    amount = int(result.get("amount_keys") or 0)
    route = ui.ROUTE_LABELS.get(decision, "выбранный")
    await query.answer(
        f"🧭 Маршрут «{route}» · +{amount} 🗝" if amount
        else f"🧭 Маршрут «{route}» выбран."
    )
    await _menu(query, db, user_id)


def _pet_label(pet: dict | None) -> str:
    return str((pet or {}).get("name") or "Питомец")
