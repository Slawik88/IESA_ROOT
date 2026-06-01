# bot/handlers/economy.py
from aiogram import Router, types

from bot.filters.text_commands import TextCmd
from infrastructure.repositories import economy as eco_db
from infrastructure.repositories import marriages as marriages_db
from infrastructure.repositories.moderation import get_chat_settings
from infrastructure.repositories.chat import get_chat_stats
from infrastructure.repositories.dark_mora import get_dark_mora_balance
from services.admin_service import give_resource, set_resource
from services.utils import resolve_target, safe_html, format_currency
from core.registry import ITEMS_REGISTRY

router = Router(name="eco_router")


@router.message(TextCmd(["баланс", "кошелек", "счет", "деньги", "кошелёк"]))
async def cmd_balance(message: types.Message, db):
    from services.utils import resolve_display_name
    user_id = message.from_user.id
    name = await resolve_display_name(db, user_id, message.chat.id, message.from_user.first_name)
    balance = await eco_db.get_balance(db, user_id)
    dark_mora = await get_dark_mora_balance(db, user_id)
    mora      = format_currency(balance['user_balance_mora'])
    diamonds  = format_currency(balance['user_balance_diamonds'])
    zarniki  = float(balance.get('user_balance_zarniki', 0) or 0)

    dark_line = f"\n├ 🌑 Тёмная Мора: <code>{dark_mora:.0f}</code>" if dark_mora > 0 else \
                f"\n├ 🌑 Тёмная Мора: <code>0</code> <i>(добыть: «бот контрабанда»)</i>"
    zarniki_line = f"\n└ ✨ Зарники: <code>{zarniki:.0f}</code>" if zarniki > 0 else ""

    text = (
        f"💳 <b>КОШЕЛЁК</b> — {name}\n\n"
        f"🪙 Мора: <code>{mora}</code>\n"
        f"💎 Алмазы: <code>{diamonds}</code>"
        f"{dark_line}"
        f"{zarniki_line}"
    )

    if message.chat.type != "private":
        marriage = await marriages_db.get_user_marriage(db, message.chat.id, user_id)
        if marriage:
            family_mora = format_currency(marriage['family_balance'])
            partner_name = marriage['user2_name'] if marriage['user1_id'] == user_id else marriage['user1_name']
            text += (
                f"\n\n🏦 <b>СЕМЕЙНЫЙ БАНК</b>\n"
                f"├ 💞 Партнёр: <b>{safe_html(partner_name)}</b>\n"
                f"└ 🪙 Общак: <code>{family_mora}</code>"
            )

    await message.answer(text, parse_mode="HTML")


@router.message(TextCmd(["перевод", "перевести", "дать", "скинуть"]))
async def cmd_pay(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return
    target_id, target_name, extra_args = await resolve_target(message, db, text_args)

    if not target_id or not extra_args:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот перевод, @юзер [сумма]</code>\n"
            "Или ответьте на сообщение пользователя.",
            parse_mode="HTML"
        )

    settings = await get_chat_settings(db, message.chat.id)
    rank_required = settings.get("rank_give", 0)
    if rank_required > 0:
        u_stats = await get_chat_stats(db, message.from_user.id, message.chat.id)
        if u_stats.get("local_rank", 0) < rank_required:
            from services import roles as _roles
            rname = _roles.LOCAL_RANKS_MAP.get(rank_required, f"Ранг {rank_required}")
            return await message.answer(
                f"❌ Переводы в этом чате доступны с ранга <b>{rname}</b> ({rank_required}+).",
                parse_mode="HTML",
            )

    if target_id == message.from_user.id:
        return await message.answer("❌ Вы не можете перевести мору самому себе.")

    try:
        amount = float(extra_args.split()[0].replace(",", "."))
    except ValueError:
        return await message.answer("❌ Укажите корректную сумму числом.")

    success, msg = await eco_db.transfer_mora(db, message.from_user.id, target_id, amount)

    if success:
        await message.answer(
            f"💸 <b>Успешный перевод!</b>\n"
            f"Вы перевели <code>{format_currency(amount)}</code> Моры пользователю <b>{safe_html(target_name)}</b>.",
            parse_mode="HTML"
        )
    else:
        await message.answer(f"❌ <b>Отказ:</b> {msg}", parse_mode="HTML")


# ==========================================
# КОМАНДЫ БОГА (ДЛЯ РАЗРАБОТЧИКА)
# ==========================================
@router.message(TextCmd(["god дать", "god выдать"]))
async def cmd_give_god(message: types.Message, db, text_args: str = None, developer_id: int = 0):
    if message.from_user.id != developer_id:
        return

    if not text_args:
        return await message.answer(
            "ℹ️ <code>бот god дать, [mora|xp|diamond|item_id] [кол-во] [target_id]</code>",
            parse_mode="HTML"
        )

    args = text_args.split()
    if len(args) < 2:
        return await message.answer("❌ Нужно минимум 2 аргумента.")

    res_type = args[0].lower()

    try:
        amount = int(args[1])
    except ValueError:
        return await message.answer("❌ Сумма/количество должно быть числом.")

    target_id = message.reply_to_message.from_user.id if message.reply_to_message else None
    if not target_id:
        try:
            target_id = int(args[-1])
        except ValueError:
            return await message.answer("❌ Не удалось найти цель.")

    item_id = res_type if res_type in ITEMS_REGISTRY else None
    actual_type = "item" if item_id else res_type

    success, result = await give_resource(db, target_id, message.chat.id, actual_type, amount, item_id)
    await message.answer(f"⚡️ <b>СИСТЕМА БОГА:</b> {'✅' if success else '❌'} {result}", parse_mode="HTML")


@router.message(TextCmd(["god установить", "god set"]))
async def cmd_set_god(message: types.Message, db, text_args: str = None, developer_id: int = 0):
    if message.from_user.id != developer_id:
        return

    if not text_args:
        return await message.answer(
            "ℹ️ <code>бот god set, [mora|diamond|xp|lvl] [значение] [target_id]</code>",
            parse_mode="HTML"
        )

    args = text_args.split()
    if len(args) < 2:
        return await message.answer("❌ Нужно минимум 2 аргумента.")

    res_type = args[0].lower()
    try:
        val = int(args[1])
    except ValueError:
        return await message.answer("❌ Значение должно быть числом.")

    target_id = message.reply_to_message.from_user.id if message.reply_to_message else None
    if not target_id and len(args) > 2:
        try:
            target_id = int(args[2])
        except ValueError:
            pass

    if not target_id:
        return await message.answer("❌ Укажите цель (реплай или ID).")

    success, result = await set_resource(db, target_id, message.chat.id, res_type, val)
    await message.answer(f"⚖️ <b>СИСТЕМА БОГА:</b> {'✅' if success else '❌'} {result}", parse_mode="HTML")
