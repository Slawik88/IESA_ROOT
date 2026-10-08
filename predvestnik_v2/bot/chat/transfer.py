"""«бот перевод, @ник 300» — перевод валюты другому игроку.

Бот спрашивает валюту кнопками; списание и зачисление идут одной транзакцией
через общий журнал экономики (economy_ledger), повторное нажатие не удваивает.
"""
from __future__ import annotations

import html
import re
from decimal import Decimal, InvalidOperation

from aiogram import Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from core.economy_contract import CURRENCY_SPECS, InsufficientBalance
from infrastructure.repositories.economy_ledger import apply_balance_change
from bot.chat import settings
from bot.chat.framework import Ctx, UsageError, registry
from bot.chat.targets import resolve_target

router = Router(name="chat_transfer")
USAGE = "бот перевод, @ник 300  (или ответом на сообщение)"
MAX_AMOUNT = Decimal("1000000000")


class TransferCB(CallbackData, prefix="tr"):
    uid: int
    to: int
    amount: str
    cur: str     # код валюты или "x" — отмена


def parse_amount(text: str) -> Decimal | None:
    m = re.search(r"(?<![\w.])(\d+(?:[.,]\d{1,2})?)(?![\w.])", text)
    if not m:
        return None
    try:
        value = Decimal(m.group(1).replace(",", "."))
    except InvalidOperation:
        return None
    return value if Decimal("0") < value <= MAX_AMOUNT else None


def fmt(value: Decimal) -> str:
    q = value.quantize(Decimal("0.01")).normalize()
    return f"{q:,f}".replace(",", " ")


@registry.command("перевод", aliases=("перевести", "передать"), usage=USAGE, section="profile",
                  summary="Перевести валюту игроку. Бот спросит, какую.", example="бот перевод, @ник 300")
async def cmd_transfer(ctx: Ctx) -> None:
    target, rest = await resolve_target(ctx.db, ctx.message, ctx.args)
    amount = parse_amount(rest)
    if target is None or amount is None:
        raise UsageError(USAGE)
    if target.user_id == ctx.user_id:
        await ctx.reply("🙂 Себе переводить не нужно.")
        return
    codes = await settings.transferable(ctx.db)
    if not codes:
        await ctx.reply("⛔ Переводы сейчас отключены.")
        return
    buttons = [
        InlineKeyboardButton(
            text=f"{CURRENCY_SPECS[c].icon} {CURRENCY_SPECS[c].label}",
            callback_data=TransferCB(uid=ctx.user_id, to=target.user_id, amount=str(amount), cur=c).pack())
        for c in codes if c in CURRENCY_SPECS
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="✖️ Отмена", callback_data=TransferCB(
        uid=ctx.user_id, to=target.user_id, amount=str(amount), cur="x").pack())])
    await ctx.reply(f"💸 Перевод {html.escape(target.label())}: <b>{fmt(amount)}</b>\nКакую валюту отправить?",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(TransferCB.filter())
async def on_transfer(call: CallbackQuery, callback_data: TransferCB, db) -> None:
    cb = callback_data
    if call.from_user.id != cb.uid:
        await call.answer("Это не ваш перевод.", show_alert=True)
        return
    if cb.cur == "x":
        await call.message.edit_text("✖️ Перевод отменён.")
        await call.answer()
        return
    if cb.cur not in await settings.transferable(db):
        await call.answer("Эту валюту сейчас переводить нельзя.", show_alert=True)
        return
    amount = parse_amount(cb.amount)
    if amount is None:
        await call.answer()
        return
    spec = CURRENCY_SPECS[cb.cur]
    if spec.display_decimals == 0 and amount != amount.to_integral_value():
        await call.answer(f"{spec.label} переводится только целым числом.", show_alert=True)
        return
    key = f"chat-transfer:{call.message.chat.id}:{call.message.message_id}"
    try:
        async with db.connection.transaction():
            await apply_balance_change(
                db, cb.uid, {cb.cur: -amount}, reason_code="player_transfer_out",
                idempotency_key=key + ":out", source_type="chat", reference_type="player_transfer",
                reference_id=key, chat_id=call.message.chat.id, target_id=cb.to)
            await apply_balance_change(
                db, cb.to, {cb.cur: amount}, reason_code="player_transfer_in",
                idempotency_key=key + ":in", source_type="chat", reference_type="player_transfer",
                reference_id=key, chat_id=call.message.chat.id, target_id=cb.uid)
    except InsufficientBalance:
        await call.answer(f"Не хватает: {spec.label}.", show_alert=True)
        return
    async with db.execute("SELECT user_tg_username FROM users WHERE user_tg_id = ?", (cb.to,)) as cur:
        row = await cur.fetchone()
    who = f"@​{row[0]}" if row and row[0] else f"id{cb.to}"
    await call.message.edit_text(
        f"✅ Переведено {html.escape(who)}: <b>{fmt(amount)}</b> {spec.icon} {spec.label}", parse_mode="HTML")
    await call.answer("Готово")
