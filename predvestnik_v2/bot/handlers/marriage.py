from aiogram import Router, types
from services.utils import resolve_target, safe_html, parse_dt, check_callback_owner
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime

from infrastructure.repositories import marriages, users
from infrastructure.repositories.marriages import create_proposal, update_proposal_status
from infrastructure.repositories.moderation import get_chat_settings
from infrastructure.repositories.chat import get_chat_stats
from services import marriage as marriage_service
from bot.filters.text_commands import TextCmd
from services.utils import format_currency

router = Router(name="marriage_router")

class MarriageAction(CallbackData, prefix="marry"):
    action: str
    target_id: int
    initiator_id: int

class DivorceConfirm(CallbackData, prefix="divorce"):
    action: str  # "confirm" | "cancel"
    user_id: int = 0

# ==========================================
# КОМАНДА 1: Предложение (/marriage)
# ==========================================
@router.message(TextCmd(["брак", "свадьба", "роспись"]))
async def cmd_marriage(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return await message.answer("❌ <b>Ошибка:</b> Браки заключаются только в группах!", parse_mode="HTML")

    initiator_id = message.from_user.id
    from services.utils import resolve_display_name
    initiator_name = await resolve_display_name(db, initiator_id, message.chat.id, message.from_user.first_name)

    settings = await get_chat_settings(db, message.chat.id)
    rank_required = settings.get("rank_marriage", 0)
    if rank_required > 0:
        u_stats = await get_chat_stats(db, initiator_id, message.chat.id)
        if u_stats.get("local_rank", 0) < rank_required:
            from services import roles as _roles
            rname = _roles.LOCAL_RANKS_MAP.get(rank_required, f"Ранг {rank_required}")
            return await message.answer(
                f"❌ Браки в этом чате доступны с ранга <b>{rname}</b> ({rank_required}+).",
                parse_mode="HTML",
            )

    target_id, target_name, extra_args = await resolve_target(message, db, text_args)

    # Умная проверка: если искали по @username, но его нет в базе
    if extra_args == "error_user_not_found":
        return await message.answer(
            "❌ <b>Пользователь не найден!</b>\n"
            "Бот его еще не запомнил. Пусть он напишет хоть одно сообщение в этот чат.", 
            parse_mode="HTML"
        )

    if not target_id:
        return await message.answer(
            f"ℹ️ <b>Как сделать предложение:</b>\n"
            f"└ Ответьте на сообщение или введите: <code>бот брак, @юзер</code>",
            parse_mode="HTML"
        )

    is_bot = False
    if message.reply_to_message and message.reply_to_message.from_user.id == target_id:
        is_bot = message.reply_to_message.from_user.is_bot
    elif target_id == message.bot.id:
        is_bot = True 

    can_marry, error_msg = await marriage_service.check_marriage_proposal(db, initiator_id, target_id, is_bot)
    if not can_marry:
        return await message.answer(error_msg, parse_mode="HTML")

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Согласиться", callback_data=MarriageAction(action="accept", target_id=target_id, initiator_id=initiator_id))
    builder.button(text="❌ Отказаться", callback_data=MarriageAction(action="decline", target_id=target_id, initiator_id=initiator_id))
    builder.adjust(2)

    target_link = f'<a href="tg://user?id={target_id}">{target_name}</a>'
    initiator_link = f'<a href="tg://user?id={initiator_id}">{initiator_name}</a>'

    text = (
        f"💍 <b>ПРЕДЛОЖЕНИЕ РУКИ И СЕРДЦА</b>\n\n"
        f"👤 {target_link}, пользователь {initiator_link} предлагает вам стать парой!\n\n"
        f"<i>Что ответите? Выбор за вами.</i>"
    )
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

    # Sync to DB so web panel can show incoming proposals
    try:
        await create_proposal(db, message.chat.id, initiator_id, target_id)
        await db.commit()
    except Exception:
        pass  # non-critical, bot inline flow still works without DB row

# ==========================================
# ОБРАБОТЧИК КНОПОК ПРЕДЛОЖЕНИЯ
# ==========================================
@router.callback_query(MarriageAction.filter())
async def process_marriage_action(callback: types.CallbackQuery, callback_data: MarriageAction, db):
    if callback.from_user.id != callback_data.target_id:
        return await callback.answer("❌ Это предложение сделали не вам!", show_alert=True)

    from services.utils import resolve_display_name
    target_name = await resolve_display_name(
        db, callback.from_user.id, callback.message.chat.id, callback.from_user.first_name
    )

    if callback_data.action == "decline":
        try:
            await update_proposal_status(db, callback.message.chat.id, callback_data.initiator_id, callback_data.target_id, "declined")
            await db.commit()
        except Exception:
            pass
        await callback.message.edit_text(
            f"💔 <b>ОТКАЗ</b>\n\n"
            f'Пользователь <a href="tg://user?id={callback_data.target_id}">{target_name}</a> отклонил предложение.',
            parse_mode="HTML"
        )
        return await callback.answer()

    can_marry, _ = await marriage_service.check_marriage_proposal(db, callback_data.initiator_id, callback_data.target_id, False)
    if not can_marry:
        await callback.message.edit_text("❌ К сожалению, предложение больше недействительно.", parse_mode="HTML")
        return await callback.answer()

    initiator_name = await users.get_user_name(db, callback_data.initiator_id)
    
    await marriages.create_marriage(
        db, callback.message.chat.id,
        callback_data.initiator_id, initiator_name,
        callback_data.target_id, target_name
    )
    try:
        await update_proposal_status(db, callback.message.chat.id, callback_data.initiator_id, callback_data.target_id, "accepted")
    except Exception:
        pass

    initiator_link = f'<a href="tg://user?id={callback_data.initiator_id}">{initiator_name}</a>'
    target_link = f'<a href="tg://user?id={callback_data.target_id}">{target_name}</a>'

    text = (
        f"🎉 <b>НОВЫЙ СОЮЗ ЗАКЛЮЧЕН!</b>\n\n"
        f"💖 В этом чате появилась новая пара:\n"
        f"├ 💫 {initiator_link}\n"
        f"└ 💫 {target_link}\n\n"
        f"<i>Желаем счастья и долгих совместных уровней! 🥂</i>"
    )
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()

# ==========================================
# Развод (/divorce)
# ==========================================
@router.message(TextCmd(["развод", "расстаться"]))
async def cmd_divorce(message: types.Message, db):
    marriage = await marriages.get_user_marriage(db, message.from_user.id)
    if not marriage:
        return await message.answer("💔 Вы и так свободны как ветер.", parse_mode="HTML")

    partner_id = marriage['user2_id'] if marriage['user1_id'] == message.from_user.id else marriage['user1_id']
    partner_name = marriage['user2_name'] if marriage['user1_id'] == message.from_user.id else marriage['user1_name']
    partner_link = f'<a href="tg://user?id={partner_id}">{safe_html(partner_name)}</a>'

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, развестись", callback_data=DivorceConfirm(action="confirm", user_id=message.from_user.id))
    builder.button(text="❌ Нет, остаться", callback_data=DivorceConfirm(action="cancel", user_id=message.from_user.id))
    builder.adjust(2)

    await message.answer(
        f"💔 <b>ПОДТВЕРЖДЕНИЕ РАЗВОДА</b>\n\n"
        f"Вы уверены, что хотите расстаться с {partner_link}?\n"
        f"<i>Семейный бюджет будет заморожен.</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(DivorceConfirm.filter())
async def process_divorce_confirm(callback: types.CallbackQuery, callback_data: DivorceConfirm, db):
    if not await check_callback_owner(callback, callback_data.user_id):
        return
    if callback_data.action == "cancel":
        await callback.message.edit_text("💍 <b>Развод отменён.</b> Семья сохранена.", parse_mode="HTML")
        return await callback.answer()

    marriage = await marriages.get_user_marriage(db, callback.from_user.id)
    if not marriage:
        await callback.message.edit_text("💔 Брак уже был расторгнут.", parse_mode="HTML")
        return await callback.answer()

    await marriages.delete_marriage(db, callback.from_user.id)
    await callback.message.edit_text("💔 <b>Брак расторгнут.</b> Вы снова свободны.", parse_mode="HTML")
    await callback.answer()

# ==========================================
# КОМАНДА 2: Моя пара (/couple)
# ==========================================
@router.message(TextCmd(["пара", "моя пара", "мой брак"]))
async def cmd_couple(message: types.Message, db):
    marriage = await marriages.get_user_marriage(db, message.from_user.id)
    
    if not marriage:
        return await message.answer("💔 Вы ещё не состоите в браке. Время найти свою половинку!", parse_mode="HTML")

    partner_id = marriage['user2_id'] if marriage['user1_id'] == message.from_user.id else marriage['user1_id']
    partner_name = marriage['user2_name'] if marriage['user1_id'] == message.from_user.id else marriage['user1_name']

    my_link = f'<a href="tg://user?id={message.from_user.id}">{safe_html(message.from_user.first_name)}</a>'
    partner_link = f'<a href="tg://user?id={partner_id}">{safe_html(partner_name)}</a>'
    
    date_obj = parse_dt(marriage['marriage_date'])
    date_str = date_obj.strftime("%d.%m.%Y")
    days_together = (datetime.now() - date_obj).days
    family_balance = marriage.get('family_balance', 0)

    text = (
        f"💍 <b>СЕМЕЙНОЕ ПОЛОЖЕНИЕ</b>\n\n"
        f"💖 <b>ПАРА</b>\n"
        f"├ 💫 {my_link}\n"
        f"└ 💫 {partner_link}\n\n"
        f"📅 <b>СТАТУС</b>\n"
        f"├ ⏳ В браке с: <code>{date_str}</code>\n"
        f"├ ❤️ Вместе уже: <code>{days_together} дн.</code>\n"
        f"└ 🏦 Общий бюджет: <code>{format_currency(family_balance)}</code> 🪙"
    )
    await message.answer(text, parse_mode="HTML")

# ==========================================
# КОМАНДА 3: Все браки чата (/all_couples)
# ==========================================
@router.message(TextCmd(["все браки", "пары", "браки чата", "пары чата"]))
async def cmd_all_couples(message: types.Message, db):
    all_m = await marriages.get_all_marriages(db, message.chat.id)
    
    if not all_m:
        return await message.answer("🕸 <b>В этом чате пока нет ни одной пары.</b>", parse_mode="HTML")

    text = f"💒 <b>БРАКИ ЭТОГО ЧАТА</b>\n\n"
    
    for idx, m in enumerate(all_m, 1):
        u1_link = f"""<a href="tg://user?id={m['user1_id']}">{safe_html(m['user1_name'])}</a>"""
        u2_link = f"""<a href="tg://user?id={m['user2_id']}">{safe_html(m['user2_name'])}</a>"""
        try:
            date_obj = parse_dt(m['marriage_date'])
            delta = datetime.now() - date_obj
            days = delta.days
            hours = delta.seconds // 3600
            duration_str = f"{days} дн. {hours} ч." if hours else f"{days} дн."
        except Exception:
            duration_str = "—"
        text += f"{idx}. 💍 {u1_link} ❤️ {u2_link} — <i>{duration_str}</i>\n"

    text += f"\n<i>💡 Всего пар в чате: <b>{len(all_m)}</b></i>"
    await message.answer(text, parse_mode="HTML")


@router.message(TextCmd(["вложить", "в общак"]))
async def cmd_family_deposit(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return

    if not text_args:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот вложить, [сумма]</code>\nПеревод вашей Моры в семейный бюджет.",
            parse_mode="HTML"
        )

    try:
        amount = float(text_args.split()[0].replace(",", "."))
    except ValueError:
        return await message.answer("❌ Укажите сумму числом.")
    
    marriage = await marriages.get_user_marriage(db, message.from_user.id)
    if not marriage: return await message.answer("❌ Вы не состоите в браке.")
    
    success, msg = await marriages.family_bank_transaction(db, marriage['id'], message.from_user.id, amount, "deposit")
    if success:
        await message.answer(f"🏦 Вы вложили <code>{format_currency(amount)}</code> Моры в семейный бюджет.\nНовый баланс семьи: <code>{format_currency(marriage['family_balance'] + amount)}</code>", parse_mode="HTML")
    else:
        await message.answer(f"❌ <b>Отказ:</b> {msg}", parse_mode="HTML")

@router.message(TextCmd(["общак", "семейный баланс", "семья"]))
async def cmd_family_info(message: types.Message, db):
    if message.chat.type == "private":
        return

    marriage = await marriages.get_user_marriage(db, message.from_user.id)
    if not marriage:
        return await message.answer("💔 Вы не состоите в браке.", parse_mode="HTML")

    partner_id = marriage['user2_id'] if marriage['user1_id'] == message.from_user.id else marriage['user1_id']
    partner_name = marriage['user2_name'] if marriage['user1_id'] == message.from_user.id else marriage['user1_name']

    my_link = f'<a href="tg://user?id={message.from_user.id}">{safe_html(message.from_user.first_name)}</a>'
    partner_link = f'<a href="tg://user?id={partner_id}">{safe_html(partner_name)}</a>'

    date_obj = parse_dt(marriage['marriage_date'])
    date_str = date_obj.strftime("%d.%m.%Y")
    days_together = (datetime.now() - date_obj).days
    family_balance = marriage.get('family_balance', 0)

    text = (
        f"🏦 <b>СЕМЕЙНЫЙ БЮДЖЕТ</b>\n\n"
        f"💑 <b>ПАРА</b>\n"
        f"├ 💫 {my_link}\n"
        f"└ 💫 {partner_link}\n\n"
        f"📅 <b>ИСТОРИЯ</b>\n"
        f"├ ⏳ В браке с: <code>{date_str}</code>\n"
        f"├ ❤️ Вместе: <code>{days_together} дн.</code>\n"
        f"└ 🏦 Общак: <code>{format_currency(family_balance)}</code> 🪙\n\n"
        f"<i>💡 Пополнить: «бот вложить, [сумма]» · Снять: «бот снять, [сумма]»</i>"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(TextCmd(["снять", "из общака"]))
async def cmd_family_withdraw(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return

    if not text_args:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот снять, [сумма]</code>\nСнятие Моры из семейного бюджета.",
            parse_mode="HTML"
        )

    try:
        amount = float(text_args.split()[0].replace(",", "."))
    except ValueError:
        return await message.answer("❌ Укажите сумму числом.")
    
    marriage = await marriages.get_user_marriage(db, message.from_user.id)
    if not marriage: return await message.answer("❌ Вы не состоите в браке.")
    
    success, msg = await marriages.family_bank_transaction(db, marriage['id'], message.from_user.id, amount, "withdraw")
    if success:
        await message.answer(f"🏦 Вы сняли <code>{format_currency(amount)}</code> Моры из семейного бюджета.\nОстаток семьи: <code>{format_currency(marriage['family_balance'] - amount)}</code>", parse_mode="HTML")
    else:
        await message.answer(f"❌ <b>Отказ:</b> {msg}", parse_mode="HTML")
