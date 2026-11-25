"""Хаб питомцев в чате: коллекция, кормление, походы, экспедиции и маршруты.

Команды совместимы со старым ботом («бот поход, 6» сразу отправляет питомца),
а те же действия доступны кнопками. Всё меняющее повторяется по токену: двойной
тап не списывает еду или выносливость дважды. Таблицы питомцев создаются при
первом заходе — как у квестов. Каркас и подсказки: `framework.py`, экраны —
`pets_views.py`, `pets_collection_views.py`, `pets_activity_views.py`.
"""
from __future__ import annotations

import re
from uuid import uuid4

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.chat import pets_activity_views as activity_ui
from bot.chat import pets_collection_views as collection_ui
from bot.chat import pets_views as ui
from bot.chat.cbutil import edit_or_send
from bot.chat.framework import Ctx, UsageError, registry
from bot.chat.modules import module_disabled_reason
from core.chests_v1 import FOODS
from infrastructure.repositories.pets_v1 import ensure_tables
from services import pets_v1
from services.formatting import safe_html

router = Router(name="chat_pets")

HUB_ALIASES = ("мои питомцы", "питомец", "мой питомец", "активный питомец", "питомци", "мои питомци", "зоопарк", "питомник")
TREK_ALIASES = ("походы",)
EXPEDITION_ALIASES = ("экспедиции",)
_ROUTE_WORDS = {
    "осторожный": "careful", "ровный": "steady", "рискованный": "bold",
    "разведка": "scout", "разведать": "scout", "разведочный": "scout",
}
_TOKEN_RE = re.compile(r"^[0-9a-f]{12}$")
_ROUTE_USAGE = "бот маршрут, осторожный|ровный|рискованный|разведка"


async def _module_off(ctx: Ctx) -> bool:
    """Модуль питомцев выключен в этом чате или глобально — сказать и остановиться."""
    if ctx.message.chat.type not in ("group", "supergroup"):
        return False
    reason = await module_disabled_reason(ctx.db, ctx.message.chat.id, "module_pets")
    if reason:
        await ctx.reply(f"🔧 {safe_html(reason)}")
        return True
    return False


async def _overview(db, user_id: int) -> dict:
    await ensure_tables(db)
    return await pets_v1.overview(db, user_id)


def parse_hours(text: str) -> int:
    value = str(text or "").strip()
    if value not in {"3", "6", "9"}:
        raise ValueError("Доступная длительность: 3, 6 или 9 часов.")
    return int(value)


def parse_route(text: str) -> str:
    """Принять русские подписи кнопок и мини-аппа: осторожный, ровный, рискованный, разведка."""
    word = str(text or "").strip().lower().replace("ё", "е")
    route = _ROUTE_WORDS.get(word)
    if route is None:
        raise ValueError("Маршрут: осторожный, ровный, рискованный или разведка (с 12 уровня).")
    return route


# ── Команды ───────────────────────────────────────────────────────────────────


@registry.command(
    "питомцы", aliases=HUB_ALIASES, usage="бот питомцы", section="pets",
    summary="Хаб питомцев: коллекция, кормление, походы и экспедиции.",
)
async def cmd_pets(ctx: Ctx) -> None:
    if await _module_off(ctx):
        return
    view = await _overview(ctx.db, ctx.user_id)
    text, markup = collection_ui.menu_view(view, user_id=ctx.user_id, pack=ui.pack_pet_callback)
    await ctx.reply(text, reply_markup=markup)


@registry.command(
    "поход", aliases=TREK_ALIASES, usage="бот поход [3|6|9]", section="pets",
    summary="Отправить активного питомца в поход на 3, 6 или 9 часов.",
    example="бот поход, 6",
)
async def cmd_trek(ctx: Ctx) -> None:
    await _activity_command(ctx, kind="trek")


@registry.command(
    "экспедиция", aliases=EXPEDITION_ALIASES, usage="бот экспедиция [3|6|9]", section="pets",
    summary="Экспедиция с выбором маршрута после таймера (ключей больше).",
    example="бот экспедиция, 6",
)
async def cmd_expedition(ctx: Ctx) -> None:
    await _activity_command(ctx, kind="expedition")


@registry.command(
    "маршрут", usage=_ROUTE_USAGE, section="pets",
    summary="Выбрать маршрут завершённой экспедиции: шанс успеха и награда.",
    example="бот маршрут, ровный",
)
async def cmd_route(ctx: Ctx) -> None:
    if await _module_off(ctx):
        return
    if ctx.args.strip():
        await _choose_route(ctx, text=ctx.args)
        return
    view = await _overview(ctx.db, ctx.user_id)
    text, markup = activity_ui.route_view(view, user_id=ctx.user_id, pack=ui.pack_pet_callback)
    await ctx.reply(text, reply_markup=markup)


@registry.command(
    "бестиарий", usage="бот бестиарий", section="pets",
    summary="Какие виды питомцев открыты, а какие ещё нет.",
)
async def cmd_bestiary(ctx: Ctx) -> None:
    if await _module_off(ctx):
        return
    view = await _overview(ctx.db, ctx.user_id)
    text, markup = collection_ui.bestiary_view(view, user_id=ctx.user_id, pack=ui.pack_pet_callback)
    await ctx.reply(text, reply_markup=markup)


@registry.command(
    "ускорить поход", aliases=("ускорить",), usage="бот ускорить поход", section="pets",
    summary="Ускорить таймер нельзя: здесь честный статус похода или экспедиции.",
)
async def cmd_speedup(ctx: Ctx) -> None:
    if await _module_off(ctx):
        return
    view = await _overview(ctx.db, ctx.user_id)
    text, markup = activity_ui.speedup_view(view, user_id=ctx.user_id, pack=ui.pack_pet_callback)
    await ctx.reply(text, reply_markup=markup)


async def _activity_command(ctx: Ctx, *, kind: str) -> None:
    if await _module_off(ctx):
        return
    if ctx.args.strip():
        await _start_activity(ctx, kind=kind, text=ctx.args)
        return
    view = await _overview(ctx.db, ctx.user_id)
    text, markup = activity_ui.activity_view(view, kind, user_id=ctx.user_id, pack=ui.pack_pet_callback)
    await ctx.reply(text, reply_markup=markup)


async def _start_activity(ctx: Ctx, *, kind: str, text: str) -> None:
    try:
        hours = parse_hours(text)
    except ValueError:
        raise UsageError(f"бот {'поход' if kind == 'trek' else 'экспедиция'}, 3|6|9") from None
    try:
        result = await pets_v1.start_activity(
            ctx.db, user_id=ctx.user_id, kind=kind, hours=hours, action_id=f"chat:{uuid4().hex}",
        )
    except pets_v1.PetPolicyError as error:
        await ctx.reply(f"❌ {safe_html(str(error))}")
        return
    title = "Поход" if kind == "trek" else "Экспедиция"
    ends = ui.format_ends_at((result.get("activity") or {}).get("ends_at"))
    await ctx.reply(
        f"🐾 <b>{title} начат</b> · {hours} ч\n"
        f"<blockquote>Финиш: <code>{ends}</code>\n"
        "Таймер у питомца один: новый старт — только после финиша.\n"
        "Заглянуть в хаб: <code>бот питомцы</code>.</blockquote>",
        reply_markup=ui.menu_button(ctx.user_id),
    )


async def _choose_route(ctx: Ctx, *, text: str) -> None:
    try:
        decision = parse_route(text)
    except ValueError:
        raise UsageError(_ROUTE_USAGE) from None
    try:
        result = await pets_v1.choose_expedition(
            ctx.db, user_id=ctx.user_id, decision=decision, action_id=f"chat-route:{uuid4().hex}",
        )
    except pets_v1.PetPolicyError as error:
        await ctx.reply(f"❌ {safe_html(str(error))}")
        return
    await ctx.reply(_route_result_text(decision, result), reply_markup=ui.menu_button(ctx.user_id))


def _route_result_text(decision: str, result: dict) -> str:
    route = result.get("route") or {}
    label = ui.ROUTE_LABELS.get(decision, decision)
    lines = [f"🧭 <b>Маршрут «{label}» выбран.</b>"]
    details: list[str] = []
    if route.get("success"):
        paid, reward = int(route.get("paid_mora") or 0), int(route.get("reward_mora") or 0)
        details.append(f"Экспедиция прошла: <b>+{paid} 🪙</b>.")
        if route.get("capped"):
            details.append(f"Недельный лимит наград: начислено {paid} из {reward} 🪙, остаток переносится на следующую неделю.")
    elif route:
        details.append("Экспедиция не прошла: <b>ничего не потеряно</b>.")
    keys = int(result.get("amount_keys") or 0)
    if keys:
        details.append(f"Ключей за экспедицию: <b>+{keys} 🗝</b>.")
    if details:
        details.append("Общий таймер освобождён.")
        lines.append("<blockquote>" + "\n".join(details) + "</blockquote>")
    return "\n".join(lines)


# ── Кнопки ────────────────────────────────────────────────────────────────────


async def _guard(call: CallbackQuery, callback_data: ui.PetsCB) -> bool:
    if call.from_user.id != int(callback_data.user_id):
        await call.answer("❌ Это меню другого игрока. Откройте своё: «бот питомцы».", show_alert=True)
        return False
    return True


async def _module_off_call(call: CallbackQuery, db) -> bool:
    message = getattr(call, "message", None)
    if message is None or message.chat.type not in ("group", "supergroup"):
        return False
    reason = await module_disabled_reason(db, message.chat.id, "module_pets")
    if reason:
        await call.answer(f"🔧 {reason}", show_alert=True)
        return True
    return False


async def _edit(call: CallbackQuery, text: str, markup) -> None:
    await edit_or_send(call, text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)


def _action_id(kind: str, token: str) -> str:
    value = str(token or "")
    if not _TOKEN_RE.fullmatch(value):
        raise pets_v1.PetPolicyError("Кнопка устарела — откройте питомцев заново: «бот питомцы».")
    return f"chat:{kind}:{value}"


async def _menu(call: CallbackQuery, db, user_id: int) -> None:
    view = await _overview(db, user_id)
    text, markup = collection_ui.menu_view(view, user_id=user_id, pack=ui.pack_pet_callback)
    await _edit(call, text, markup)


async def _fail(call: CallbackQuery, db, user_id: int, error: Exception) -> None:
    await call.answer(f"❌ {error}", show_alert=True)
    await _menu(call, db, user_id)


@router.callback_query(ui.PetsCB.filter(F.action == "menu"))
async def cb_pet_menu(call: CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(call, callback_data) or await _module_off_call(call, db):
        return
    await call.answer()
    await _menu(call, db, int(callback_data.user_id))


@router.callback_query(ui.PetsCB.filter(F.action == "pets"))
async def cb_pet_list(call: CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(call, callback_data) or await _module_off_call(call, db):
        return
    user_id = int(callback_data.user_id)
    await call.answer()
    view = await _overview(db, user_id)
    text, markup = collection_ui.pets_view(view, user_id=user_id, pack=ui.pack_pet_callback)
    await _edit(call, text, markup)


@router.callback_query(ui.PetsCB.filter(F.action == "pet"))
async def cb_pet_card(call: CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(call, callback_data) or await _module_off_call(call, db):
        return
    user_id = int(callback_data.user_id)
    await call.answer()
    view = await _overview(db, user_id)
    text, markup = collection_ui.pet_card_view(
        view, int(callback_data.pet_id), user_id=user_id, pack=ui.pack_pet_callback,
    )
    await _edit(call, text, markup)


@router.callback_query(ui.PetsCB.filter(F.action == "best"))
async def cb_pet_bestiary(call: CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(call, callback_data) or await _module_off_call(call, db):
        return
    user_id = int(callback_data.user_id)
    await call.answer()
    view = await _overview(db, user_id)
    text, markup = collection_ui.bestiary_view(view, user_id=user_id, pack=ui.pack_pet_callback)
    await _edit(call, text, markup)


@router.callback_query(ui.PetsCB.filter(F.action == "act"))
async def cb_pet_activity_chooser(call: CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(call, callback_data) or await _module_off_call(call, db):
        return
    user_id = int(callback_data.user_id)
    kind = str(callback_data.value) if str(callback_data.value) in ui.ACTIVITY_TITLES else "trek"
    await call.answer()
    view = await _overview(db, user_id)
    text, markup = activity_ui.activity_view(view, kind, user_id=user_id, pack=ui.pack_pet_callback)
    await _edit(call, text, markup)


@router.callback_query(ui.PetsCB.filter(F.action == "feed"))
async def cb_pet_feed_chooser(call: CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(call, callback_data) or await _module_off_call(call, db):
        return
    user_id = int(callback_data.user_id)
    await call.answer()
    view = await _overview(db, user_id)
    text, markup = collection_ui.feed_view(
        view, int(callback_data.pet_id), user_id=user_id, pack=ui.pack_pet_callback,
    )
    await _edit(call, text, markup)


@router.callback_query(ui.PetsCB.filter(F.action == "activate"))
async def cb_pet_activate(call: CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(call, callback_data) or await _module_off_call(call, db):
        return
    user_id, pet_id = int(callback_data.user_id), int(callback_data.pet_id)
    try:
        await pets_v1.select_active_pet(db, user_id, pet_id, _action_id("active", callback_data.token))
    except pets_v1.PetPolicyError as error:
        await _fail(call, db, user_id, error)
        return
    view = await _overview(db, user_id)
    pet = ui.find_pet(view, pet_id)
    await call.answer(f"⭐ {ui.pet_name(pet or {})} — теперь активный спутник.")
    text, markup = collection_ui.pet_card_view(view, pet_id, user_id=user_id, pack=ui.pack_pet_callback)
    await _edit(call, text, markup)


@router.callback_query(ui.PetsCB.filter(F.action == "food"))
async def cb_pet_feed(call: CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(call, callback_data) or await _module_off_call(call, db):
        return
    user_id, pet_id = int(callback_data.user_id), int(callback_data.pet_id)
    food_id = str(callback_data.value)
    try:
        result = await pets_v1.feed_pet(
            db, user_id=user_id, pet_id=pet_id, food_id=food_id,
            action_id=_action_id("feed", callback_data.token),
        )
    except pets_v1.PetPolicyError as error:
        await _fail(call, db, user_id, error)
        return
    food = FOODS.get(food_id) or {}
    await call.answer(
        f"{food.get('icon') or '🍖'} +{int(food.get('restore') or 0)} → "
        f"{int(result.get('endurance') or 0)}/100 · осталось {int(result.get('remaining') or 0)} шт."
    )
    view = await _overview(db, user_id)
    text, markup = collection_ui.pet_card_view(view, pet_id, user_id=user_id, pack=ui.pack_pet_callback)
    await _edit(call, text, markup)


@router.callback_query(ui.PetsCB.filter(F.action == "start"))
async def cb_pet_start(call: CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(call, callback_data) or await _module_off_call(call, db):
        return
    user_id = int(callback_data.user_id)
    kind = str(callback_data.value) if str(callback_data.value) in ui.ACTIVITY_TITLES else "trek"
    hours = int(callback_data.amount)
    if hours not in (3, 6, 9):
        await call.answer("Кнопка устарела — откройте питомцев заново: «бот питомцы».", show_alert=True)
        return
    try:
        result = await pets_v1.start_activity(
            db, user_id=user_id, kind=kind, hours=hours, action_id=_action_id("start", callback_data.token),
        )
    except pets_v1.PetPolicyError as error:
        await _fail(call, db, user_id, error)
        return
    activity = result.get("activity") or {}
    await call.answer(
        f"{ui.ACTIVITY_TITLES[kind]} · {hours} ч · финиш {ui.format_ends_at(activity.get('ends_at'))}"
        f" · ⚡ {int(result.get('endurance') or 0)}/100"
    )
    await _menu(call, db, user_id)


@router.callback_query(ui.PetsCB.filter(F.action == "route"))
async def cb_pet_route(call: CallbackQuery, callback_data: ui.PetsCB, db) -> None:
    if not await _guard(call, callback_data) or await _module_off_call(call, db):
        return
    user_id = int(callback_data.user_id)
    decision = str(callback_data.value)
    if decision not in ui.ROUTE_LABELS:
        await call.answer("Кнопка устарела — откройте питомцев заново: «бот питомцы».", show_alert=True)
        return
    try:
        result = await pets_v1.choose_expedition(
            db, user_id=user_id, decision=decision, action_id=_action_id("route", callback_data.token),
        )
    except pets_v1.PetPolicyError as error:
        await _fail(call, db, user_id, error)
        return
    route = result.get("route") or {}
    label = ui.ROUTE_LABELS.get(decision, decision)
    if route.get("success"):
        tail = f"+{int(route.get('paid_mora') or 0)} 🪙"
    elif route:
        tail = "без потерь"
    else:
        tail = "маршрут записан"
    await call.answer(f"🧭 «{label}»: {tail}")
    await _menu(call, db, user_id)
