# DEPRECATED — МЁРТВЫЙ КОД (БЛОК19 «Web First»): роутер этого файла НЕ зарегистрирован
# в bot/handlers/__init__.py::main_router — ни одна команда/кнопка отсюда не выполняется.
# Механика живёт в мини-аппе (FastAPI/), чат-алиасы ловит web_redirect.py.
# Файл оставлен как референс. НЕ подключать без ревизии: тексты/поля могли устареть.
"""bot/handlers/craft.py — Crafting UI."""
from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from bot.filters.text_commands import TextCmd
from core.registry import CRAFT_RECIPES, ITEMS_REGISTRY
from infrastructure.repositories.economy import get_item_quantity
from services import global_moderation
from services.craft import get_craftable_list, craft
from services.utils import check_callback_owner

router = Router(name="craft_router")


class CraftCB(CallbackData, prefix="craft"):
    action: str     # "list" | "confirm" | "do"
    recipe_id: str = ""
    user_id: int = 0


def _ingredient_line(ing: dict) -> str:
    status = "✅" if ing["ok"] else "❌"
    return f"{status} {ing['item_name']} — <code>{ing['have']}/{ing['needed']}</code>"


def _build_list_text(recipes: list[dict]) -> str:
    lines = ["⚗️ <b>КРАФТ</b>\n"]
    for r in recipes:
        can = "✅ Можно" if r["can_craft"] else "🔒 Не хватает"
        times = f" (×{r['can_craft_times']})" if r["can_craft_times"] > 1 else ""
        lines.append(f"{'═' * 20}\n{r['name']}  {can}{times}")
        # у рецептов нет поля desc (есть what_is) — раньше тут был гарантированный KeyError
        lines.append(r.get("what_is") or r.get("desc") or "")
        lines.append("<b>Ингредиенты:</b>")
        for ing in r["ingredients_status"]:
            lines.append(f"  {_ingredient_line(ing)}")
    lines.append("\n<i>Нажмите кнопку рецепта чтобы скрафтить.</i>")
    return "\n".join(lines)


def _list_keyboard(recipes: list[dict], user_id: int) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for r in recipes:
        label = f"{'🔨' if r['can_craft'] else '🔒'} {r['name']}"
        if r["can_craft_times"] > 1:
            label += f" ×{r['can_craft_times']}"
        b.button(
            text=label,
            callback_data=CraftCB(action="confirm", recipe_id=r["recipe_id"], user_id=user_id),
        )
    b.adjust(1)
    return b.as_markup()


def _confirm_keyboard(recipe_id: str, user_id: int) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text="✅ Скрафтить",
        callback_data=CraftCB(action="do", recipe_id=recipe_id, user_id=user_id),
    )
    b.button(
        text="❌ Отмена",
        callback_data=CraftCB(action="list", recipe_id="", user_id=user_id),
    )
    b.adjust(2)
    return b.as_markup()


@router.message(TextCmd(["крафт", "craft", "скрафтить", "создать предмет"]))
async def cmd_craft(message: types.Message, db, text_args: str = None,
                     user_restricted: dict | None = None, chat_restricted: dict | None = None):
    restriction = user_restricted or chat_restricted
    if restriction:
        return await message.answer(global_moderation.restriction_message(restriction))

    recipes = await get_craftable_list(db, message.from_user.id)
    if not recipes:
        return await message.answer("⚗️ <b>КРАФТ</b>\n\n<i>Рецептов пока нет.</i>", parse_mode="HTML")

    # Direct craft shortcut: бот крафт, жетон / бот крафт, summon_token
    if text_args:
        arg = text_args.strip().lower()
        matched = next(
            (r for r in recipes if arg in r["recipe_id"].lower() or arg in r["name"].lower()),
            None,
        )
        if matched:
            if not matched["can_craft"]:
                missing = [i for i in matched["ingredients_status"] if not i["ok"]]
                lines = ["❌ <b>Отказ:</b> не хватает ингредиентов:"]
                for m in missing:
                    lines.append(f"  · {m['item_name']}: нужно {m['needed']}, есть {m['have']}")
                return await message.answer("\n".join(lines), parse_mode="HTML")

            recipe = CRAFT_RECIPES[matched["recipe_id"]]
            return await message.answer(
                f"⚗️ <b>Крафт: {recipe['name']}</b>\n\n"
                f"Потратить: <b>{', '.join(f'{n}× {i}' for i, n in recipe['ingredients'])}</b>\n"
                f"Получить: <b>1× {recipe['name']}</b>\n\n"
                f"<i>Подтвердить?</i>",
                reply_markup=_confirm_keyboard(matched["recipe_id"], message.from_user.id),
                parse_mode="HTML",
            )

    text = _build_list_text(recipes)
    kb = _list_keyboard(recipes, message.from_user.id)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(CraftCB.filter(F.action == "list"))
async def cb_craft_list(query: types.CallbackQuery, callback_data: CraftCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    recipes = await get_craftable_list(db, query.from_user.id)
    text = _build_list_text(recipes)
    kb = _list_keyboard(recipes, callback_data.user_id)
    try:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await query.answer()


@router.callback_query(CraftCB.filter(F.action == "confirm"))
async def cb_craft_confirm(query: types.CallbackQuery, callback_data: CraftCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    recipe = CRAFT_RECIPES.get(callback_data.recipe_id)
    if not recipe:
        return await query.answer("Рецепт не найден.", show_alert=True)

    lines = [f"⚗️ <b>Крафт: {recipe['name']}</b>\n"]
    for item_id, needed in recipe["ingredients"]:
        have = await get_item_quantity(db, query.from_user.id, item_id)
        iname = ITEMS_REGISTRY.get(item_id, {}).get("name", item_id)
        status = "✅" if have >= needed else "❌"
        lines.append(f"{status} {iname}: <code>{have}/{needed}</code>")

    lines.append(f"\n→ Получить: <b>1× {recipe['name']}</b>")
    lines.append("\n<i>Подтвердить?</i>")

    try:
        await query.message.edit_text(
            "\n".join(lines),
            reply_markup=_confirm_keyboard(callback_data.recipe_id, callback_data.user_id),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    await query.answer()


@router.callback_query(CraftCB.filter(F.action == "do"))
async def cb_craft_do(query: types.CallbackQuery, callback_data: CraftCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return

    result = await craft(db, query.from_user.id, callback_data.recipe_id)

    if not result["ok"]:
        await query.answer(f"❌ {result['reason']}", show_alert=True)
        # Refresh list
        recipes = await get_craftable_list(db, query.from_user.id)
        try:
            await query.message.edit_text(
                _build_list_text(recipes),
                reply_markup=_list_keyboard(recipes, callback_data.user_id),
                parse_mode="HTML",
            )
        except TelegramBadRequest:
            pass
        return

    await db.commit()
    await query.answer(f"✅ Скрафтено: {result['name']}!", show_alert=False)

    # Show updated list
    recipes = await get_craftable_list(db, query.from_user.id)
    try:
        await query.message.edit_text(
            f"🎉 <b>Готово!</b> Получено: <b>{result['name']}</b>!\n\n"
            + _build_list_text(recipes),
            reply_markup=_list_keyboard(recipes, callback_data.user_id),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
