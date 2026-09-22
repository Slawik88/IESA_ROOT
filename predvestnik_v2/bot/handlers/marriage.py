from aiogram import Bot, Router, types
from services.utils import resolve_target, safe_html, parse_dt, check_callback_owner
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime

from infrastructure.repositories import marriages, users
from infrastructure.repositories.marriages import (
    create_proposal, update_proposal_status, FAMILY_CURRENCIES,
)
from infrastructure.repositories.family_wallet_v1 import (
    FamilyTransferIntentError,
    consume_telegram_transfer_intent,
    create_telegram_transfer_intent,
)
from infrastructure.repositories import divorce_v1
from core.economy_contract import IdempotencyConflict, InsufficientBalance, InvalidEconomicMutation
from core.registry import PARTNER_GIFTS
from infrastructure.repositories.moderation import get_chat_settings
from infrastructure.repositories.chat import get_chat_stats
from services import marriage as marriage_service
from bot.filters.text_commands import TextCmd
from services.utils import format_currency, resolve_display_name
from bot.handlers.economy import PayCB  # переиспользуем выбор валюты для «подарка» партнёру
from bot.keyboards.cta import answer_group_only

router = Router(name="marriage_router")

class MarriageAction(CallbackData, prefix="marry"):
    action: str
    target_id: int
    initiator_id: int

class DivorceConfirm(CallbackData, prefix="divorce"):
    action: str  # "confirm" | "cancel"
    intent_id: str

class FamilyBankCB(CallbackData, prefix="fbank"):
    cur: str          # mora / diamonds / dark_mora / zarniki
    intent_id: str

class GiftBuyCB(CallbackData, prefix="gbuy"):
    gift_id: str
    buyer_id: int
    partner_id: int


def _gift_price_str(gift: dict) -> str:
    if gift.get("price_mora"):     return f"{gift['price_mora']} 🪙"
    if gift.get("price_diamonds"): return f"{gift['price_diamonds']} 💎"
    if gift.get("price_zarniki"):  return f"{gift['price_zarniki']} ✨"
    return "—"


def _family_currency_kb(intent_id: str):
    """Currency choices for one persisted, owner-bound transfer intent."""
    b = InlineKeyboardBuilder()
    for cur, meta in FAMILY_CURRENCIES.items():
        b.button(text=f"{meta['icon']} {meta['label']}",
                 callback_data=FamilyBankCB(cur=cur, intent_id=intent_id))
    b.adjust(2, 2)
    return b

# ==========================================
# КОМАНДА 1: Предложение (/marriage)
# ==========================================
@router.message(TextCmd(["брак", "свадьба", "роспись"]))
async def cmd_marriage(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return await answer_group_only(message)

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
            "ℹ️ <b>Как сделать предложение:</b>\n"
            "└ Ответьте на сообщение или введите: <code>бот брак, @юзер</code>",
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

    target_name = await resolve_display_name(db, target_id, message.chat.id, target_name)

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
    
    try:
        await marriages.create_marriage(
            db, callback.message.chat.id,
            callback_data.initiator_id, initiator_name,
            callback_data.target_id, target_name
        )
    except marriages.MarriageConflict as exc:
        await callback.message.edit_text(f"❌ {exc}", parse_mode="HTML")
        return await callback.answer()
    except RuntimeError:
        await callback.message.edit_text(
            "⚠️ Создание брака временно остановлено для безопасного переноса данных.",
            parse_mode="HTML",
        )
        return await callback.answer()
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
    try:
        intent = await divorce_v1.create_intent(db, actor_id=message.from_user.id)
    except divorce_v1.DivorceError:
        return await message.answer("💔 Вы и так свободны как ветер.", parse_mode="HTML")

    partner_link = f'<a href="tg://user?id={intent["partner_id"]}">{safe_html(intent["partner_name"])}</a>'
    blocked = any(float(value or 0) != 0 for value in (
        *intent["legacy_balances"], *intent["custody_balances"],
    )) or int(intent["family_pet_count"]) > 0

    builder = InlineKeyboardBuilder()
    if not blocked:
        builder.button(text="✅ Да, развестись", callback_data=DivorceConfirm(action="confirm", intent_id=intent["id"]))
    else:
        builder.button(
            text="⚖️ Разделить и развестись",
            callback_data=DivorceConfirm(action="split", intent_id=intent["id"]),
        )
    builder.button(text="❌ Нет, остаться", callback_data=DivorceConfirm(action="cancel", intent_id=intent["id"]))
    builder.adjust(2)

    asset_note = (
        "\n\n🏦 <b>Развод пока заблокирован:</b> в семье остались средства или семейные питомцы. "
            "Кнопка ниже поровну распределит средства, передаст питомцев и сразу завершит брак. "
            "Это необратимое действие; бот ничего не удалит и сохранит квитанции."
        if blocked else "\n\nПосле подтверждения брак будет закрыт, а оба игрока смогут создать новую семью."
    )
    await message.answer(
        f"💔 <b>ПОДТВЕРЖДЕНИЕ РАЗВОДА</b>\n\n"
        f"Вы уверены, что хотите расстаться с {partner_link}?\n"
        f"<i>Подтверждение действует 15 минут.</i>{asset_note}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(DivorceConfirm.filter())
async def process_divorce_confirm(
    callback: types.CallbackQuery, callback_data: DivorceConfirm, db, bot: Bot,
):
    if callback_data.action == "split":
        try:
            allocation = await divorce_v1.allocate_property(
                db, intent_id=callback_data.intent_id, actor_id=callback.from_user.id,
            )
        except divorce_v1.DivorceError as exc:
            await callback.message.edit_text(
                f"⚖️ <b>Раздел не выполнен.</b> {safe_html(str(exc))}", parse_mode="HTML",
            )
            return await callback.answer()
        replay = " Повторного перевода не было." if not allocation.applied else ""
        await callback.message.edit_text(
            "💔 <b>Брак расторгнут, имущество распределено.</b>\n\n"
            "Средства разделены поровну, а питомцы по очереди переданы обоим бывшим партнёрам.\n"
            f"Квитанция имущества: <code>{allocation.receipt_id}</code>\n"
            f"Квитанция развода: <code>{allocation.divorce_receipt_id}</code>{replay}",
            parse_mode="HTML",
        )
        if allocation.applied:
            try:
                await bot.send_message(
                    allocation.partner_id,
                    "💔 Ваш брак завершён партнёром. Семейные средства распределены поровну, "
                    "питомцы переданы владельцам, ничего не удалено.\n"
                    f"Квитанция имущества: <code>{allocation.receipt_id}</code>\n"
                    f"Квитанция развода: <code>{allocation.divorce_receipt_id}</code>",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        return await callback.answer("Имущество распределено, брак завершён")
    if callback_data.action == "cancel":
        cancelled = await divorce_v1.cancel_intent(
            db, intent_id=callback_data.intent_id, actor_id=callback.from_user.id,
        )
        if not cancelled:
            return await callback.answer("Подтверждение уже обработано или принадлежит другому игроку.", show_alert=True)
        await callback.message.edit_text("💍 <b>Развод отменён.</b> Семья сохранена.", parse_mode="HTML")
        return await callback.answer()
    try:
        result = await divorce_v1.settle_intent(
            db, intent_id=callback_data.intent_id, actor_id=callback.from_user.id,
        )
    except divorce_v1.DivorceError as exc:
        await callback.message.edit_text(f"🏦 <b>Развод не выполнен.</b> {safe_html(str(exc))}", parse_mode="HTML")
        return await callback.answer()
    replay = " Повторного изменения не было." if not result.applied else ""
    await callback.message.edit_text(
        f"💔 <b>Брак расторгнут.</b> Вы снова свободны.\n"
        f"Квитанция: <code>{result.receipt_id}</code>{replay}", parse_mode="HTML",
    )
    if result.applied:
        try:
            await bot.send_message(
                result.partner_id,
                "💔 Ваш брак был расторгнут партнёром. Семейная история сохранена, "
                f"квитанция: <code>{result.receipt_id}</code>.", parse_mode="HTML",
            )
        except Exception:
            pass
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

    text = "💒 <b>БРАКИ ЭТОГО ЧАТА</b>\n\n"
    
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
        # Двухстрочно: пара имён отдельно от длительности — с двумя длинными
        # именами подряд строка легко рвала перенос на узком экране.
        text += f"{idx}. 💍 {u1_link} ❤️ {u2_link}\n    <i>{duration_str}</i>\n"

    text += f"\n<i>💡 Всего пар в чате: <b>{len(all_m)}</b></i>"
    await message.answer(text, parse_mode="HTML")


def _parse_bank_amount(text_args: str | None):
    if not text_args:
        return None
    try:
        return float(text_args.split()[0].replace(",", "."))
    except ValueError:
        return None


@router.message(TextCmd(["вложить", "в общак"]))
async def cmd_family_deposit(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return await answer_group_only(message)
    amount = _parse_bank_amount(text_args)
    if amount is None:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот вложить, [сумма]</code>\nПеревод вашей валюты в семейный кошелёк.",
            parse_mode="HTML")
    if amount <= 0:
        return await message.answer("❌ Сумма должна быть больше нуля.")
    try:
        intent_id = await create_telegram_transfer_intent(
            db, actor_id=message.from_user.id, action="deposit", amount=amount,
        )
    except (FamilyTransferIntentError, InvalidEconomicMutation) as exc:
        return await message.answer(f"❌ {safe_html(str(exc))}", parse_mode="HTML")
    kb = _family_currency_kb(intent_id)
    await message.answer(
        f"📥 Вложить <b>{format_currency(amount)}</b> в семейный кошелёк — какой валютой?",
        reply_markup=kb.as_markup(), parse_mode="HTML")


@router.message(TextCmd(["снять", "из общака"]))
async def cmd_family_withdraw(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return await answer_group_only(message)
    amount = _parse_bank_amount(text_args)
    if amount is None:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот снять, [сумма]</code>\nСнятие валюты из семейного кошелька.",
            parse_mode="HTML")
    if amount <= 0:
        return await message.answer("❌ Сумма должна быть больше нуля.")
    try:
        intent_id = await create_telegram_transfer_intent(
            db, actor_id=message.from_user.id, action="withdrawal", amount=amount,
        )
    except (FamilyTransferIntentError, InvalidEconomicMutation) as exc:
        return await message.answer(f"❌ {safe_html(str(exc))}", parse_mode="HTML")
    kb = _family_currency_kb(intent_id)
    await message.answer(
        f"📤 Снять <b>{format_currency(amount)}</b> из семейного кошелька — какой валютой?",
        reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(FamilyBankCB.filter())
async def cb_family_bank(query: types.CallbackQuery, callback_data: FamilyBankCB, db):
    meta = FAMILY_CURRENCIES.get(callback_data.cur)
    if not meta:
        return await query.answer("Неизвестная валюта.", show_alert=True)
    try:
        result = await consume_telegram_transfer_intent(
            db, intent_id=callback_data.intent_id, actor_id=query.from_user.id,
            currency=callback_data.cur,
        )
    except FamilyTransferIntentError as exc:
        return await query.answer(str(exc), show_alert=True)
    except InsufficientBalance as exc:
        return await query.answer(str(exc), show_alert=True)
    except (IdempotencyConflict, InvalidEconomicMutation) as exc:
        return await query.answer(str(exc), show_alert=True)
    if not result.applied:
        text = "✅ <b>Этот выбор уже обработан.</b> Повторного перевода не было."
    else:
        verb = "вложили в" if result.action == "deposit" else "сняли из"
        wallet = "семейный кошелёк" if result.action == "deposit" else "семейного кошелька"
        text = f"🏦 Вы {verb} {wallet}: <code>{format_currency(result.amount)}</code> {meta['icon']} {meta['label']}."
    try:
        await query.message.edit_text(text, parse_mode="HTML")
    except Exception:
        await query.message.answer(text, parse_mode="HTML")
    await query.answer()


@router.message(TextCmd(["общак", "семейный баланс", "семья"]))
async def cmd_family_info(message: types.Message, db):
    if message.chat.type == "private":
        return await answer_group_only(message)

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

    # Все 4 валюты семейного кошелька (показываем только ненулевые + Мору всегда)
    wallet_lines = []
    for cur, meta in FAMILY_CURRENCIES.items():
        bal = float(marriage.get(meta["fam_col"], 0) or 0)
        if bal > 0 or cur == "mora":
            wallet_lines.append(f"{meta['icon']} {format_currency(bal)} {meta['label']}")
    wallet_str = " · ".join(wallet_lines)

    text = (
        f"🏦 <b>СЕМЕЙНЫЙ КОШЕЛЁК</b>\n\n"
        f"💑 <b>ПАРА</b>\n"
        f"├ 💫 {my_link}\n"
        f"└ 💫 {partner_link}\n\n"
        f"📅 <b>ИСТОРИЯ</b>\n"
        f"├ ⏳ В браке с: <code>{date_str}</code>\n"
        f"└ ❤️ Вместе: <code>{days_together} дн.</code>\n\n"
        f"💰 <b>КОШЕЛЁК:</b> {wallet_str}\n\n"
        f"<i>Внести: «бот вложить, сумма» · снять: «бот снять, сумма».\n"
        f"Каждый перевод получает отдельную квитанцию. Памятный подарок: «бот подарки»</i>"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(TextCmd(["подарок", "подарить партнёру", "подарить партнеру", "подарок партнёру"]))
async def cmd_gift_partner(message: types.Message, db, text_args: str = None):
    """Подарить партнёру любую валюту (Block 5.3). Авто-цель — супруг.
    Переиспользует PayCB / cb_pay_currency из economy.py."""
    return await message.answer("🎁 Прямые переводы валюты закрыты. Памятные подарки без игровой силы доступны по команде «бот подарки».")
    if message.chat.type == "private":
        return await answer_group_only(message)
    amount = _parse_bank_amount(text_args)
    if amount is None:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот подарок, [сумма]</code>\nПодарок валютой вашему партнёру.",
            parse_mode="HTML")
    if amount <= 0:
        return await message.answer("❌ Сумма должна быть больше нуля.")
    marriage = await marriages.get_user_marriage(db, message.from_user.id)
    if not marriage:
        return await message.answer("💔 Вы не состоите в браке.")
    partner_id = marriage['user2_id'] if marriage['user1_id'] == message.from_user.id else marriage['user1_id']
    partner_name = await resolve_display_name(db, partner_id, message.chat.id,
                                              marriage['user2_name'] if marriage['user1_id'] == message.from_user.id else marriage['user1_name'])
    b = InlineKeyboardBuilder()
    for cur, meta in FAMILY_CURRENCIES.items():
        b.button(text=f"{meta['icon']} {meta['label']}",
                 callback_data=PayCB(cur=cur, target_id=partner_id, amount=amount,
                                     sender_id=message.from_user.id))
    b.adjust(2, 2)
    await message.answer(
        f"🎁 Подарить <b>{format_currency(amount)}</b> партнёру <b>{partner_name}</b> — какой валютой?",
        reply_markup=b.as_markup(), parse_mode="HTML")


# ── Каталог подарков партнёру (Block 5.4) ────────────────────────────────────
@router.message(TextCmd(["подарки", "подарки партнёру", "витрина подарков", "магазин подарков"]))
async def cmd_gift_catalog(message: types.Message, db):
    if message.chat.type == "private":
        return await answer_group_only(message)
    marriage = await marriages.get_user_marriage(db, message.from_user.id)
    if not marriage:
        return await message.answer("💔 Сначала найдите свою половинку — подарки дарятся партнёру.")
    partner_id = marriage['user2_id'] if marriage['user1_id'] == message.from_user.id else marriage['user1_id']
    partner_name = await resolve_display_name(db, partner_id, message.chat.id,
                                              marriage['user2_name'] if marriage['user1_id'] == message.from_user.id else marriage['user1_name'])
    lines = ["🎁 <b>ПОДАРКИ ПАРТНЁРУ</b>", f"Для: <b>{partner_name}</b>\n"]
    b = InlineKeyboardBuilder()
    for gid, g in PARTNER_GIFTS.items():
        tag = "🎀 память"
        lines.append(f"{g['name']} — {_gift_price_str(g)} <i>({tag})</i>")
        b.button(text=f"{g['name']} · {_gift_price_str(g)}",
                 callback_data=GiftBuyCB(gift_id=gid, buyer_id=message.from_user.id, partner_id=partner_id))
    b.adjust(1)
    lines.append("\n<i>Подарки сохраняются в семейной истории и не меняют силу, XP или награды.</i>")
    await message.answer("\n".join(lines), reply_markup=b.as_markup(), parse_mode="HTML")


@router.callback_query(GiftBuyCB.filter())
async def cb_gift_buy(query: types.CallbackQuery, callback_data: GiftBuyCB, db):
    if query.from_user.id != callback_data.buyer_id:
        return await query.answer("Это не ваш подарок.", show_alert=True)
    ok, msg, gift = await marriages.purchase_partner_gift(
        db, callback_data.buyer_id, callback_data.partner_id, callback_data.gift_id,
        idempotency_key=f"telegram:partner-gift:{query.id}",
    )
    if not ok:
        return await query.answer(msg, show_alert=True)
    partner_name = await resolve_display_name(db, callback_data.partner_id,
                                              query.message.chat.id, "партнёру")
    buyer_name = await resolve_display_name(db, callback_data.buyer_id,
                                            query.message.chat.id, query.from_user.first_name)
    try:
        await query.message.edit_text(
            f"🎁 <b>{buyer_name}</b> {msg} — <b>{partner_name}</b> 💖",
            parse_mode="HTML")
    except Exception:
        await query.message.answer(f"🎁 {msg}", parse_mode="HTML")
    await query.answer("Подарок вручён! 💖")
