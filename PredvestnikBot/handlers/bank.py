"""
Банк Северного Королевства — вклады с процентами.

Команды:
  бот банк / бот вклад   — меню банка (создать вклад / просмотр / снять)
"""

from datetime import datetime, timedelta

from aiogram import Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import BANK_EARLY_PENALTY, BANK_MAX_DEPOSIT, BANK_MIN_DEPOSIT, BANK_PLANS
from database.db import (
    add_mora,
    create_deposit,
    deduct_mora,
    get_mora,
    get_user_deposits,
    withdraw_deposit,
)
from filters.bot_command import BotCommand

router = Router()

_PLAN_LABELS = {
    "short":  "📅 Короткий",
    "medium": "📆 Средний",
    "long":   "📋 Долгий",
}


def _plan_desc(key: str) -> str:
    p = BANK_PLANS[key]
    label = _PLAN_LABELS.get(key, key)
    pct = int(p["rate"] * 100)
    return f"{label} — {p['days']} д., +{pct}%"


# ─── бот банк ─────────────────────────────────────────────────────────────────

@router.message(BotCommand("банк", "вклад", "bank", "deposit"))
async def cmd_bank(message: Message, cmd_args: str):
    if message.chat.type == "private":
        await message.answer("❌ Банк доступен только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    mora = await get_mora(uid, chat_id)
    bal = mora["balance"] if mora else 0
    deposits = await get_user_deposits(uid, chat_id)

    lines = [
        "🏦 <b>Банк Северного Королевства</b>\n",
        f"💰 Баланс: <b>{bal} 🪙</b>\n",
        "📊 <b>Планы вкладов:</b>",
    ]
    for key in ("short", "medium", "long"):
        lines.append(f"  • {_plan_desc(key)}")

    lines.append(f"\n⚠️ Досрочное снятие: штраф <b>{int(BANK_EARLY_PENALTY * 100)}%</b> от суммы\n")

    if deposits:
        lines.append("📦 <b>Твои вклады:</b>")
        now = datetime.utcnow()
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
            text=f"➕ {_plan_desc(key)}",
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
            callback_data=f"bank_confirm:{owner}:{plan_key}:{amt}",
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


# ─── Подтверждение вклада ─────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("bank_confirm:"))
async def cb_bank_confirm(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner = int(parts[1])
    plan_key = parts[2]
    amount = int(parts[3])

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

    ok, new_bal = await deduct_mora(uid, chat_id, amount)
    if not ok:
        mora = await get_mora(uid, chat_id)
        bal = mora["balance"] if mora else 0
        await callback.answer(f"❌ Недостаточно Моры ({bal} / {amount})", show_alert=True)
        return

    await create_deposit(uid, chat_id, amount, p["rate"], p["days"])

    reward = int(amount * p["rate"])
    try:
        await callback.message.edit_text(
            f"✅ <b>Вклад открыт!</b>\n\n"
            f"💳 Сумма: {amount} 🪙\n"
            f"📊 Доход: +{reward} 🪙 через {p['days']} д.\n"
            f"💰 Баланс: {new_bal} 🪙",
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

    now = datetime.utcnow()
    dep = deposits[0]  # Снимаем первый
    dep_id = dep["id"]
    amount = dep["amount"]
    matures_at = dep["matures_at"]
    if isinstance(matures_at, str):
        matures_at = datetime.fromisoformat(matures_at)

    is_mature = now >= matures_at

    dep_data = await withdraw_deposit(dep_id)
    if not dep_data:
        await callback.answer("❌ Вклад уже снят.", show_alert=True)
        return

    rate = dep_data["rate"]
    if is_mature:
        payout = amount + int(amount * rate)
    else:
        payout = amount - int(amount * BANK_EARLY_PENALTY)
        if payout < 0:
            payout = 0

    await add_mora(uid, chat_id, payout)

    if is_mature:
        text = (
            f"✅ <b>Вклад #{dep_id} снят!</b>\n\n"
            f"💰 Возврат: {amount} 🪙 + {payout - amount} 🪙 проценты\n"
            f"💳 Получено: <b>{payout} 🪙</b>"
        )
    else:
        penalty = int(amount * BANK_EARLY_PENALTY)
        text = (
            f"⚠️ <b>Вклад #{dep_id} снят досрочно!</b>\n\n"
            f"💰 Сумма: {amount} 🪙\n"
            f"📉 Штраф: -{penalty} 🪙\n"
            f"💳 Получено: <b>{payout} 🪙</b>"
        )

    try:
        await callback.message.edit_text(text, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer()
