"""Chat-side pet hub: full pet management from Telegram (commands + buttons).

Commands stay backward compatible («бот поход, 6» still starts the timer), but
the same actions are now reachable by buttons: activation, feeding, activities
and the expedition route, with the bestiary and a collection list on top.
"""
from __future__ import annotations

import uuid

from aiogram import Router, types

from bot.filters.text_commands import TextCmd
from bot.handlers import _pets_ui as ui
from bot.handlers._pets_ui import render_pet_overview  # noqa: F401  (re-exported contract)
from bot.handlers.pets_v1_callbacks import router as pets_callbacks_router
from bot.middlewares.module_check_mw import ModuleCheckMiddleware
from infrastructure.repositories.pets_v1 import ensure_tables
from services import pets_v1
from services.utils import safe_html

router = Router(name="pets_v1_router")
router.message.middleware(ModuleCheckMiddleware("module_pets"))
router.callback_query.middleware(ModuleCheckMiddleware("module_pets"))
router.include_router(pets_callbacks_router)

HUB_ALIASES = [
    "питомцы", "мои питомцы", "питомец", "мой питомец", "активный питомец",
    "питомци", "мои питомци", "зоопарк", "питомник",
]
TREK_ALIASES = ["поход", "походы"]
EXPEDITION_ALIASES = ["экспедиция", "экспедиции"]


def parse_activity_hours(text_args: str) -> int:
    value = str(text_args or "").strip()
    if value not in {"3", "6", "9"}:
        raise ValueError("Доступная длительность: 3, 6 или 9 часов.")
    return int(value)


def parse_expedition_route(text_args: str) -> str:
    """Accept only the three clear Russian chat labels for the Mini App choices."""
    routes = {"осторожный": "careful", "ровный": "steady", "рискованный": "bold"}
    normalized = str(text_args or "").strip().lower()
    if normalized not in routes:
        raise ValueError("Маршрут: осторожный, ровный или рискованный.")
    return routes[normalized]


async def _send_view(message: types.Message, view, build) -> None:
    text, markup = build(view)
    await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.message(TextCmd(HUB_ALIASES))
async def cmd_pets_v1(message: types.Message, db, text_args: str = "") -> None:
    """Pet hub: collection, feeding, activities and the bestiary by buttons."""
    del text_args
    user_id = int(message.from_user.id)
    view = await pets_v1.chat_overview(db, user_id)
    await _send_view(message, view, lambda data: ui.menu_view(data, user_id=user_id, pack=ui.pack_pet_callback))


@router.message(TextCmd(["бестиарий"]))
async def cmd_pet_bestiary(message: types.Message, db, text_args: str = "") -> None:
    del text_args
    user_id = int(message.from_user.id)
    view = await pets_v1.chat_overview(db, user_id)
    await _send_view(message, view, lambda data: ui.bestiary_view(data, user_id=user_id, pack=ui.pack_pet_callback))


async def _start_activity(message: types.Message, db, *, kind: str, text_args: str) -> None:
    try:
        hours = parse_activity_hours(text_args)
        await ensure_tables(db)
        await pets_v1.start_activity(
            db, user_id=int(message.from_user.id), kind=kind, hours=hours,
            action_id=f"chat:{uuid.uuid4().hex}",
        )
    except (ValueError, pets_v1.PetPolicyError) as error:
        await message.answer(f"❌ {safe_html(str(error))}", parse_mode="HTML")
        return
    title = "Поход" if kind == "trek" else "Экспедиция"
    await message.answer(
        f"🐾 <b>{title} начат</b>\nДлительность: <b>{hours} ч</b>.\n"
        "Это единственный общий таймер питомца — повторный запуск будет отклонён.\n"
        "Проверить состояние: <code>бот питомцы</code>.",
        parse_mode="HTML",
        reply_markup=ui.menu_button(int(message.from_user.id)),
    )


async def _activity_command(message: types.Message, db, *, kind: str, text_args: str) -> None:
    """Without arguments show the button chooser; with a duration start directly."""
    if str(text_args or "").strip():
        await _start_activity(message, db, kind=kind, text_args=text_args)
        return
    user_id = int(message.from_user.id)
    view = await pets_v1.chat_overview(db, user_id)
    await _send_view(message, view, lambda data: ui.activity_view(data, kind, user_id=user_id, pack=ui.pack_pet_callback))


@router.message(TextCmd(TREK_ALIASES))
async def cmd_pet_trek(message: types.Message, db, text_args: str = "") -> None:
    await _activity_command(message, db, kind="trek", text_args=text_args)


@router.message(TextCmd(EXPEDITION_ALIASES))
async def cmd_pet_expedition(message: types.Message, db, text_args: str = "") -> None:
    await _activity_command(message, db, kind="expedition", text_args=text_args)


async def _choose_route(message: types.Message, db, *, text_args: str) -> None:
    try:
        decision = parse_expedition_route(text_args)
        await ensure_tables(db)
        result = await pets_v1.choose_expedition(
            db, user_id=int(message.from_user.id), decision=decision,
            action_id=f"chat-route:{uuid.uuid4().hex}",
        )
    except (ValueError, pets_v1.PetPolicyError) as error:
        await message.answer(f"❌ {safe_html(str(error))}", parse_mode="HTML")
        return
    await message.answer(
        f"🧭 <b>Выбран {ui.ROUTE_LABELS[decision]} маршрут.</b>\n"
        f"Экспедиция завершена. Получено: <b>{int(result.get('amount_keys') or 0)} 🗝</b>; "
        "общий таймер освобождён.",
        parse_mode="HTML",
        reply_markup=ui.menu_button(int(message.from_user.id)),
    )


@router.message(TextCmd(["маршрут"]))
async def cmd_expedition_route(message: types.Message, db, text_args: str = "") -> None:
    """Route buttons after the timer, or the explicit «бот маршрут, ровный» form."""
    if str(text_args or "").strip():
        await _choose_route(message, db, text_args=text_args)
        return
    user_id = int(message.from_user.id)
    view = await pets_v1.chat_overview(db, user_id)
    await _send_view(message, view, lambda data: ui.route_view(data, user_id=user_id, pack=ui.pack_pet_callback))


@router.message(TextCmd(["ускорить поход"]))
async def cmd_speedup_trek(message: types.Message, db, text_args: str = "") -> None:
    """Timers run in real time; explain it and offer the current state instead."""
    del text_args
    user_id = int(message.from_user.id)
    view = await pets_v1.chat_overview(db, user_id)
    await _send_view(message, view, lambda data: ui.speedup_view(data, user_id=user_id, pack=ui.pack_pet_callback))
