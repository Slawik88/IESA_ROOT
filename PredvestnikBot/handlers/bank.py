"""
Банк Северного Королевства — вклады с процентами.

Команды:
  бот банк / бот вклад   — меню банка (создать вклад / просмотр / снять)
"""

from datetime import datetime, timedelta, timezone

from aiogram import Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import BANK_EARLY_PENALTY_PCT, BANK_MAX_DEPOSIT, BANK_MIN_DEPOSIT, BANK_PLANS, MINI_APP_TG_URL
from database.db import (
    add_mora,
    add_to_family_wallet,
    create_deposit,
    get_family_wallet,
    get_mora,
    get_total_family_balance,
    get_user_deposits,
    is_user_single,
    withdraw_deposit,
)
from filters.bot_command import BotCommand
from handlers.economy import deduct_wallet

from filters.chat_mode import MainChatOnly
import logging
_log = logging.getLogger(__name__)
router = Router()
router.message.filter(MainChatOnly())


_PLAN_LABELS = {
    "short":  "📅 Короткий",
    "medium": "📆 Средний",
    "long":   "📋 Долгий",
}


# Бонус одиночки: +2% к любому вкладу
SINGLES_BANK_BONUS = 0.02


def _plan_desc(key: str, singles_bonus: bool = False) -> str:
    p = BANK_PLANS[key]
    label = _PLAN_LABELS.get(key, key)
    base_rate = p["rate"]
    effective_rate = base_rate + SINGLES_BANK_BONUS if singles_bonus else base_rate
    pct = int(effective_rate * 100)
    bonus_tag = " 💼" if singles_bonus else ""
    return f"{label} — {p['days']} д., +{pct}%{bonus_tag}"


# ─── бот банк ─────────────────────────────────────────────────────────────────

@router.message(BotCommand("банк", "вклад", "bank", "deposit"))
async def cmd_bank(message: Message, cmd_args: str):
    if message.chat.type == "private":
        await message.answer("❌ Банк доступен только в группах.")
        return

    # PHASE 3: Bank → Mini App in groups
    abs_cid = abs(message.chat.id)
    btn = InlineKeyboardButton(
        text="🏦 Банк в Mini App",
        url=f"{MINI_APP_TG_URL}?startapp={abs_cid}_bank",
    )
    await message.answer(
        "🏦 <b>Банк переехал в Mini App!</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[btn]]),
    )
    return

    uid = message.from_user.id
    chat_id = message.chat.id
    mora = await get_mora(uid, chat_id)
    bal = mora["balance"] if mora else 0
    deposits = await get_user_deposits(uid, chat_id)
    single = await is_user_single(uid, chat_id)

    lines = [
        "🏦 <b>Банк Северного Королевства</b>​",
        f"💰 Баланс: <b>{bal} 🪙</b>\n",
    ]
    if single:
        lines.append("💼 <i>Бафф одиночки: Ваши ставки повышены на 2%!</i>\n")
    lines.append("📊 <b>Планы вкладов:</b>")
    for key in ("short", "medium", "long"):
        lines.append(f"  • {_plan_desc(key, single)}")

    lines.append(f"\n⚠️ Досрочное снятие: потеря ВСЕХ процентов + штраф <b>{int(BANK_EARLY_PENALTY_PCT * 100)}%</b> от вклада\n")

    if deposits:
        lines.append("📦 <b>Твои вклады:</b>")
        now = datetime.now(timezone.utc)
        for dep in deposits:
            amount = dep["amount"]
            rate = dep["rate"]
            reward = int(amount * rate)
            matures_at = dep["matures_at"]
            if isinstance(matures_at, str):
                matures_at = datetime.fromisoformat(matures_at)
            if now >= matures_at:
                status = "✅ Готов к снятию"
            else:
                left = matures_at - now
                hrs = int(left.total_seconds() // 3600)
                status = f"⏳ Ещё {hrs} ч."
            pct = int(rate * 100)
            lines.append(
                f"  #{dep['id']} | {amount} 🪙 → +{reward} 🪙 | {pct}% | {status}"
            )
    else:
        lines.append("📦 <i>Вкладов нет.</i>")

    # Кнопки
    buttons = []
    for key in ("short", "medium", "long"):
        buttons.append([InlineKeyboardButton(
            text=f"➕ {_plan_desc(key, single)}",
            callback_data=f"bank_open:{uid}:{key}",
        )])
    if deposits:
        buttons.append([InlineKeyboardButton(
            text="💸 Снять первый готовый вклад",
            callback_data=f"bank_withdraw:{uid}",
        )])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)


# ─── Открыть вклад (ввод суммы) ──────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("bank_open:"))
async def cb_bank_open(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner = int(parts[1])
    plan_key = parts[2]

    if callback.from_user.id != owner:
        await callback.answer("❌ Это не твой банк!", show_alert=True)
        return

    p = BANK_PLANS.get(plan_key)
    if not p:
        await callback.answer("❌ Неверный план.", show_alert=True)
        return

    # Предлагаем фиксированные суммы
    amounts = [a for a in (100, 250, 500, 1000) if BANK_MIN_DEPOSIT <= a <= BANK_MAX_DEPOSIT]
    buttons = []
    for amt in amounts:
        buttons.append(InlineKeyboardButton(
            text=f"{amt} 🪙",
            callback_data=f"bank_source:{owner}:{plan_key}:{amt}",
        ))
    kb = InlineKeyboardMarkup(inline_keyboard=[buttons[:2], buttons[2:]])

    pct = int(p["rate"] * 100)
    try:
        await callback.message.edit_text(
            f"🏦 <b>Открыть вклад: {_PLAN_LABELS.get(plan_key, plan_key)}</b>\n\n"
            f"Срок: {p['days']} дней\n"
            f"Процент: +{pct}%\n\n"
            f"Выбери сумму вклада:",
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception:
        pass
    await callback.answer()


# ─── Выбор источника средств ──────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("bank_source:"))
async def cb_bank_source_select(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner = int(parts[1])
    plan_key = parts[2]
    amount = int(parts[3])

    if callback.from_user.id != owner:
        await callback.answer("❌ Это не твой банк!", show_alert=True)
        return

    uid = owner
    chat_id = callback.message.chat.id
    mora = await get_mora(uid, chat_id)
    personal_bal = mora["balance"] if mora else 0
    total_family_bal, _, _ = await get_total_family_balance(chat_id, uid)
    single = await is_user_single(uid, chat_id)
    p = BANK_PLANS.get(plan_key)
    effective_rate = p["rate"] + (SINGLES_BANK_BONUS if single else 0.0)

    buttons = []
    if personal_bal >= amount:
        buttons.append([InlineKeyboardButton(
            text=f"💰 Личные средства ({personal_bal} 🪙)",
            callback_data=f"bank_confirm:{owner}:{plan_key}:{amount}:personal",
        )])
    else:
        buttons.append([InlineKeyboardButton(
            text=f"💰 Личные средства ({personal_bal} 🪙) - недостаточно",
            callback_data="disabled",
        )])
    
    if total_family_bal >= amount:
        buttons.append([InlineKeyboardButton(
            text=f"👨‍👩‍👧‍👦 Семейные средства ({total_family_bal} 🪙)",
            callback_data=f"bank_confirm:{owner}:{plan_key}:{amount}:family",
        )])
    else:
        buttons.append([InlineKeyboardButton(
            text=f"👨‍👩‍👧‍👦 Семейные средства ({total_family_bal} 🪙) - недостаточно",
            callback_data="disabled",
        )])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    pct = int(effective_rate * 100)
    singles_note = "\n💼 <i>Бафф одиночки: +2% к ставке!</i>" if single else ""
    try:
        await callback.message.edit_text(
            f"🏦 <b>Открыть вклад: {_PLAN_LABELS.get(plan_key, plan_key)}</b>\n\n"
            f"💳 Сумма: <b>{amount} 🪙</b>\n"
            f"📅 Срок: {p['days']} дней\n"
            f"📊 Процент: +{pct}%{singles_note}\n\n"
            f"💰 Выбери способ оплаты:",
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception:
        pass
    await callback.answer()


# ─── Подтверждение вклада ─────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("bank_confirm:"))
async def cb_bank_confirm(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner = int(parts[1])
    plan_key = parts[2]
    amount = int(parts[3])
    source = parts[4] if len(parts) > 4 else "personal"  # backward compat

    if callback.from_user.id != owner:
        await callback.answer("❌ Это не твой банк!", show_alert=True)
        return

    uid = owner
    chat_id = callback.message.chat.id
    p = BANK_PLANS.get(plan_key)
    if not p:
        await callback.answer("❌ Неверный план.", show_alert=True)
        return

    if not (BANK_MIN_DEPOSIT <= amount <= BANK_MAX_DEPOSIT):
        await callback.answer(
            f"❌ Сумма должна быть {BANK_MIN_DEPOSIT}–{BANK_MAX_DEPOSIT} 🪙",
            show_alert=True,
        )
        return

    from api.bank import deposit as _api_deposit
    try:
        res = await _api_deposit(uid, chat_id, plan_key, amount, source)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return

    payment_text = "семейного кошелька" if source == "family" else "личного баланса"
    singles_line = "\n💼 <i>(Бафф одиночки +2% применён)</i>" if res["singles_bonus"] else ""
    try:
        await callback.message.edit_text(
            f"✅ <b>Вклад открыт!</b>\n\n"
            f"💳 Сумма: {amount} 🪙 с {payment_text}\n"
            f"📊 Доход: +{res['reward']} 🪙 через {p['days']} д.{singles_line}\n",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer("✅ Вклад создан!")


# ─── Снять первый доступный вклад ────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("bank_withdraw:"))
async def cb_bank_withdraw(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner = int(parts[1])

    if callback.from_user.id != owner:
        await callback.answer("❌ Это не твой банк!", show_alert=True)
        return

    uid = owner
    chat_id = callback.message.chat.id

    deposits = await get_user_deposits(uid, chat_id)
    if not deposits:
        await callback.answer("📦 У тебя нет вкладов.", show_alert=True)
        return

    dep_id = deposits[0]["id"]
    from api.bank import withdraw as _api_withdraw
    try:
        res = await _api_withdraw(uid, chat_id, dep_id)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return

    payout = res["payout"]
    amount = res["amount"]
    if not res["early"]:
        text = (
            f"✅ <b>Вклад #{dep_id} снят!</b>\n\n"
            f"💰 Возврат: {amount} 🪙 + {payout - amount} 🪙 проценты\n"
            f"💳 Получено: <b>{payout} 🪙</b>"
        )
    else:
        penalty = amount - payout
        text = (
            f"⚠️ <b>Вклад #{dep_id} снят досрочно!</b>\n\n"
            f"💰 Сумма вклада: {amount} 🪙\n"
            f"📉 Проценты: 0 (потеряны)\n"
            f"📉 Штраф {int(BANK_EARLY_PENALTY_PCT * 100)}%: -{penalty} 🪙\n"
            f"💳 Получено: <b>{payout} 🪙</b>"
        )

    try:
        await callback.message.edit_text(text, parse_mode="HTML")
    except Exception as _e:
        _log.debug("%s", _e)
    await callback.answer()
