"""
💸 Переводы и долги — операции с Морой между участниками чата.

Команды:
  бот перевести @user N       — безвозмездно отдать Мору
  бот долг @user N            — дать Мору в долг (ждёт возврата)
  бот долги                   — список активных займов (дал и должен)
  бот вернуть долг [@user]    — вернуть долг кредитору
"""
import html

from aiogram import Router
from aiogram.types import Message

from api.economy import transfer_mora as _api_transfer
from config import LOAN_MAX_ACTIVE, LOAN_MAX_AMOUNT, MORA_TRANSFER_MAX, MORA_TRANSFER_MIN
from database.db import (
    create_loan,
    get_active_loans_as_borrower,
    get_active_loans_as_lender,
    get_mora,
    get_user,
    get_user_by_username,
    repay_loan,
)
from filters.bot_command import BotCommand
from utils.helpers import resolve_target, user_mention

from filters.chat_mode import MainChatOnly
router = Router()
router.message.filter(MainChatOnly())



# ─── бот перевести @user N ─────────────────────────────────────────────────────

@router.message(BotCommand(
    "перевести", "отправить мору", "передать мору", "transfer мору",
    "отдать мору", "скинуть мору",
))
async def cmd_transfer(message: Message, cmd_args: str):
    """Безвозмездный перевод Моры другому участнику."""
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда доступна только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id

    target_id, target_name, rest = await resolve_target(message, cmd_args)
    if target_id is None:
        await message.answer(
            "❌ Укажи получателя и сумму.\n"
            "Пример: <code>бот перевести @user 100</code>\n"
            "или реплай: <code>бот перевести 100</code>",
            parse_mode="HTML",
        )
        return

    if target_id == uid:
        await message.answer("❌ Нельзя переводить самому себе.")
        return

    amount_str = (rest or "").strip()
    try:
        amount = round(float(amount_str.replace(',', '.')), 2)
        if amount <= 0:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer(
            "❌ Укажи сумму числом.\n"
            "Пример: <code>бот перевести @user 100</code>",
            parse_mode="HTML",
        )
        return

    if amount < MORA_TRANSFER_MIN:
        await message.answer(
            f"❌ Минимальная сумма перевода: <b>{MORA_TRANSFER_MIN} 🪙</b>", parse_mode="HTML"
        )
        return
    if amount > MORA_TRANSFER_MAX:
        await message.answer(
            f"❌ Максимальная сумма перевода за раз: <b>{MORA_TRANSFER_MAX} 🪙</b>", parse_mode="HTML"
        )
        return

    try:
        res = await _api_transfer(uid, target_id, chat_id, amount)
    except ValueError as e:
        await message.answer(f"❌ {e}", parse_mode="HTML")
        return

    tax = res["tax"]
    sender = user_mention(uid, message.from_user.full_name)
    receiver = user_mention(target_id, target_name)
    tax_note = f"\n🏦 Налог казны: <b>-{tax} 🪙</b>" if tax else ""
    await message.answer(
        f"💸 <b>Перевод выполнен!</b>\n\n"
        f"{sender} → {receiver}\n"
        f"Сумма: <b>{amount} 🪙</b>{tax_note}\n\n"
        f"Твой баланс: <b>{res['from_balance']} 🪙</b>",
        parse_mode="HTML",
    )


# ─── бот долг @user N ─────────────────────────────────────────────────────────

@router.message(BotCommand("дать в долг", "дать долг", "занять мору", "loan", "дать займ"))
async def cmd_give_loan(message: Message, cmd_args: str):
    """Дать Мору в долг (заёмщик обязан вернуть)."""
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда доступна только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id

    target_id, target_name, rest = await resolve_target(message, cmd_args)
    if target_id is None:
        await message.answer(
            "❌ Укажи заёмщика и сумму.\n"
            f"Пример: <code>бот дать в долг @user 200</code>\n"
            f"Максимум займа: <b>{LOAN_MAX_AMOUNT} 🪙</b>",
            parse_mode="HTML",
        )
        return

    if target_id == uid:
        await message.answer("❌ Нельзя давать в долг самому себе.")
        return

    amount_str = (rest or "").strip()
    try:
        amount = round(float(amount_str.replace(',', '.')), 2)
        if amount <= 0:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer(
            "❌ Укажи сумму числом.\n"
            "Пример: <code>бот дать в долг @user 200</code>",
            parse_mode="HTML",
        )
        return

    if amount > LOAN_MAX_AMOUNT:
        await message.answer(
            f"❌ Максимальная сумма займа: <b>{LOAN_MAX_AMOUNT} 🪙</b>", parse_mode="HTML"
        )
        return

    # Лимит активных займов у заёмщика
    borrower_loans = await get_active_loans_as_borrower(target_id, chat_id)
    if len(borrower_loans) >= LOAN_MAX_ACTIVE:
        await message.answer(
            f"❌ У {html.escape(target_name)} уже <b>{len(borrower_loans)}</b> активных долга "
            f"(максимум {LOAN_MAX_ACTIVE}).",
            parse_mode="HTML",
        )
        return

    ok, from_bal, loan_id = await create_loan(uid, target_id, chat_id, amount)
    if not ok:
        mora = await get_mora(uid, chat_id)
        bal = mora["balance"] if mora else 0
        await message.answer(
            f"❌ Недостаточно Моры.\n"
            f"У тебя: <b>{bal} 🪙</b>, нужно: <b>{amount} 🪙</b>",
            parse_mode="HTML",
        )
        return

    lender = user_mention(uid, message.from_user.full_name)
    borrower = user_mention(target_id, target_name)
    lender_uname = message.from_user.username
    repay_hint = (
        f"<code>бот вернуть долг @{lender_uname}</code>"
        if lender_uname
        else f"<code>бот вернуть долг</code> (ID займа: #{loan_id})"
    )
    await message.answer(
        f"📋 <b>Заём №{loan_id} выдан!</b>\n\n"
        f"💰 {lender} дал в долг <b>{amount} 🪙</b> → {borrower}\n\n"
        f"Твой баланс: <b>{from_bal} 🪙</b>\n"
        f"<i>Вернуть: {repay_hint}</i>",
        parse_mode="HTML",
    )


# ─── бот долги ────────────────────────────────────────────────────────────────

@router.message(BotCommand("долги", "мои долги", "долг список", "loans", "debts", "займы"))
async def cmd_loans_list(message: Message, cmd_args: str):
    """Список активных долгов: выданных и полученных."""
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда доступна только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id

    given = await get_active_loans_as_lender(uid, chat_id)
    received = await get_active_loans_as_borrower(uid, chat_id)

    if not given and not received:
        await message.answer("✅ У тебя нет активных долгов.")
        return

    lines = ["📊 <b>Мои долги</b>\n"]

    if given:
        total_given = sum(l["amount"] for l in given)
        lines.append(f"💳 <b>Я дал в долг</b> (итого {total_given} 🪙):")
        for loan in given:
            borrower_row = await get_user(loan["borrower_id"])
            bname = html.escape(borrower_row["full_name"]) if borrower_row else str(loan["borrower_id"])
            date_str = loan["loaned_at"][:10]
            lines.append(f"  • {bname}: <b>{loan['amount']} 🪙</b>  <i>#{loan['id']} от {date_str}</i>")
        lines.append("")

    if received:
        total_owed = sum(l["amount"] for l in received)
        lines.append(f"💸 <b>Я должен</b> (итого {total_owed} 🪙):")
        for loan in received:
            lender_row = await get_user(loan["lender_id"])
            lname = html.escape(lender_row["full_name"]) if lender_row else str(loan["lender_id"])
            date_str = loan["loaned_at"][:10]
            lines.append(f"  • {lname}: <b>{loan['amount']} 🪙</b>  <i>#{loan['id']} от {date_str}</i>")
        lines.append("")
        lines.append("<i>Вернуть: <code>бот вернуть долг @кредитор</code></i>")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ─── бот вернуть долг [@user] ─────────────────────────────────────────────────

@router.message(BotCommand("вернуть долг", "отдать долг", "repay", "вернуть займ", "погасить долг"))
async def cmd_repay_loan(message: Message, cmd_args: str):
    """Вернуть долг кредитору (полностью)."""
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда доступна только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id

    received = await get_active_loans_as_borrower(uid, chat_id)
    if not received:
        await message.answer("✅ У тебя нет активных долгов.")
        return

    # Попытка определить конкретного кредитора
    lender_id = None
    lender_name = None

    if message.reply_to_message and message.reply_to_message.from_user:
        lender_id = message.reply_to_message.from_user.id
        lender_name = message.reply_to_message.from_user.full_name
    elif cmd_args:
        arg = cmd_args.strip().split()[0]
        if arg.startswith("@"):
            row = await get_user_by_username(arg)
            if row:
                lender_id = row["user_id"]
                lender_name = row["full_name"]
        elif arg.isdigit():
            row = await get_user(int(arg))
            if row:
                lender_id = row["user_id"]
                lender_name = row["full_name"]

    if lender_id is not None:
        loans = [l for l in received if l["lender_id"] == lender_id]
        if not loans:
            await message.answer(
                f"❌ У тебя нет долгов перед <b>{html.escape(lender_name or str(lender_id))}</b>.",
                parse_mode="HTML",
            )
            return
    else:
        # Без указания кредитора — берём самый старый долг
        loans = received

    # Выбираем самый старый долг (первый в списке — он упорядочен по loaned_at ASC)
    loan = loans[0]
    lender_row = await get_user(loan["lender_id"])
    lname = html.escape(lender_row["full_name"]) if lender_row else str(loan["lender_id"])

    ok, new_bal = await repay_loan(loan["id"], uid, chat_id)
    if not ok:
        mora = await get_mora(uid, chat_id)
        bal = mora["balance"] if mora else 0
        await message.answer(
            f"❌ Недостаточно Моры для погашения долга.\n"
            f"Долг: <b>{loan['amount']} 🪙</b>\n"
            f"У тебя: <b>{bal} 🪙</b>",
            parse_mode="HTML",
        )
        return

    borrower = user_mention(uid, message.from_user.full_name)
    remaining = len(received) - 1
    suffix = f"\n<i>Ещё активных долгов: {remaining}</i>" if remaining > 0 else "\n✅ Все долги погашены!"
    await message.answer(
        f"✅ <b>Долг №{loan['id']} погашен!</b>\n\n"
        f"{borrower} вернул <b>{loan['amount']} 🪙</b> → {lname}\n"
        f"Твой баланс: <b>{new_bal} 🪙</b>{suffix}",
        parse_mode="HTML",
    )
