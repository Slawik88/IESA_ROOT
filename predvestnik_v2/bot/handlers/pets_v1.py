"""Read-only Telegram view for the approved pet foundation."""
from __future__ import annotations

import os
from uuid import uuid4

from aiogram import Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from bot.middlewares.module_check_mw import ModuleCheckMiddleware
from infrastructure.repositories.pets_v1 import ensure_tables
from services import pets_v1
from services.utils import safe_html


router = Router(name="pets_v1_router")
router.message.middleware(ModuleCheckMiddleware("module_pets"))
router.callback_query.middleware(ModuleCheckMiddleware("module_pets"))
_BOT = os.getenv("BOT_USERNAME", "IIIPredvestnikIIIBot").strip().lstrip("@")


def render_pet_overview(view: dict) -> str:
    """Render the owner's pet snapshot without exposing a pet action in chat."""
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
                names = {"careful": "осторожный", "steady": "ровный", "bold": "рискованный"}
                activity_line = f"\n\n✅ <b>{label}: выбран {names.get(activity['decision'], 'маршрут')} маршрут.</b> Ключ уже зачислен."
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
        active = " · <b>активный</b>" if pet.get("active") else ""
        effects = pet.get("effects") or {}
        stage = safe_html(str(effects.get("visual_stage") or "Начальный облик"))
        lines.extend([
            f"• <b>{safe_html(str(pet.get('name') or 'Питомец'))}</b> · уровень {int(pet['level'])}{active}",
            f"  Выносливость: <b>{int(pet['endurance'])}/100</b> · {stage}",
        ])
    lines.extend([
        "",
        "Активный питомец теряет выносливость постепенно. Смена активного слота выполняется только в Mini App и защищена от повторов.",
        "За завершённый поход или экспедицию выдаётся один ключ. Кормление доступно в Mini App.",
    ])
    return "\n".join(lines) + activity_line


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


@router.message(TextCmd(["мои питомцы", "питомцы", "питомец"]))
async def cmd_pets_v1(message: types.Message, db, text_args: str = "") -> None:
    """Show only the caller's projected pet state and link to the Mini App."""
    del text_args
    user_id = int(message.from_user.id)
    await ensure_tables(db)
    view = await pets_v1.overview(db, user_id)
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🐾 Открыть питомцев", url=f"https://t.me/{_BOT}?startapp=pets")
    await message.answer(render_pet_overview(view), reply_markup=keyboard.as_markup(), parse_mode="HTML")


async def _start_activity(message: types.Message, db, *, kind: str, text_args: str) -> None:
    try:
        hours = parse_activity_hours(text_args)
        await ensure_tables(db)
        result = await pets_v1.start_activity(
            db, user_id=int(message.from_user.id), kind=kind, hours=hours, action_id=f"chat:{uuid4().hex}",
        )
    except (ValueError, pets_v1.PetPolicyError, pets_v1.PetConflict) as error:
        await message.answer(f"❌ {safe_html(str(error))}", parse_mode="HTML")
        return
    activity = result["activity"]
    title = "Поход" if kind == "trek" else "Экспедиция"
    await message.answer(
        f"🐾 <b>{title} начат</b>\nДлительность: <b>{hours} ч</b>.\n"
        "Это единственный общий таймер питомца — повторный запуск будет отклонён.\n"
        "Проверить состояние: <code>бот питомцы</code>.", parse_mode="HTML",
    )


@router.message(TextCmd(["поход"]))
async def cmd_pet_trek(message: types.Message, db, text_args: str = "") -> None:
    await _start_activity(message, db, kind="trek", text_args=text_args)


@router.message(TextCmd(["экспедиция"]))
async def cmd_pet_expedition(message: types.Message, db, text_args: str = "") -> None:
    await _start_activity(message, db, kind="expedition", text_args=text_args)


@router.message(TextCmd(["маршрут"]))
async def cmd_expedition_route(message: types.Message, db, text_args: str = "") -> None:
    """Use the same durable route decision as the Mini App after a timer ends."""
    try:
        decision = parse_expedition_route(text_args)
        await ensure_tables(db)
        result = await pets_v1.choose_expedition(
            db, user_id=int(message.from_user.id), decision=decision, action_id=f"chat-route:{uuid4().hex}",
        )
    except (ValueError, pets_v1.PetPolicyError, pets_v1.PetConflict) as error:
        await message.answer(f"❌ {safe_html(str(error))}", parse_mode="HTML")
        return
    names = {"careful": "осторожный", "steady": "ровный", "bold": "рискованный"}
    await message.answer(
        f"🧭 <b>Выбран {names[decision]} маршрут.</b>\n"
        f"Экспедиция завершена. Получено: <b>{int(result.get('amount_keys') or 0)} 🗝</b>; общий таймер освобождён.", parse_mode="HTML",
    )
