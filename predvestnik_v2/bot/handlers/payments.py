# bot/handlers/payments.py
"""Покупка ✨ Зарников за Telegram Stars (XTR) — Implementation Block 1.2/1.5.
Growth-полиш 2026-07-13: реферальная программа тоже здесь — /start ref<id> и
комиссия с покупок логически неотделимы от денежного потока Зарников."""
import os
from aiogram import Router, types, F, Bot
from aiogram.filters import CommandStart, CommandObject, BaseFilter
from aiogram.filters.callback_data import CallbackData
from aiogram.types import LabeledPrice
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from infrastructure.repositories import economy as eco_db
from core.constants import (
    ZARNIKI_PER_STAR, STARS_PACKAGES, STARS_MOST_POPULAR,
    REFERRAL_SIGNUP_MORA, REFERRAL_SIGNUP_DIAMONDS, REFERRAL_SIGNUP_VIP_DAYS,
)
from services.referral import register_referral, pay_purchase_commission

router = Router(name="payments_router")
_BOT_USERNAME = os.getenv("BOT_USERNAME", "IIIPredvestnikIIIBot")

_CUSTOM_AMOUNT_MARKER = "✏️ Введите количество ⭐ для покупки Зарников"
_MAX_STARS = 100_000


class BuyZarnikiCB(CallbackData, prefix="buyzar"):
    stars: int  # 0 = "своя сумма"


def _packages_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for stars, base, bonus in STARS_PACKAGES:
        total = base + bonus
        popular_mark = " 🔥" if stars == STARS_MOST_POPULAR else ""
        builder.button(
            text=f"{stars}⭐ → {total}✨{popular_mark}",
            callback_data=BuyZarnikiCB(stars=stars),
        )
    builder.button(text="✏️ Своя сумма", callback_data=BuyZarnikiCB(stars=0))
    builder.adjust(2)
    return builder


async def _send_packages_menu(message: types.Message):
    lines = ["✨ <b>ЗАРНИКИ</b> — донат-валюта Предвестника\n"]
    for stars, base, bonus in STARS_PACKAGES:
        total = base + bonus
        popular = " — <b>самое популярное!</b> 🔥" if stars == STARS_MOST_POPULAR else ""
        lines.append(f"├ {stars}⭐ = {base} + {bonus} бонус = <b>{total}✨</b>{popular}")
    lines.append("\n💡 Своя сумма: 1⭐ = 10✨ (без бонуса)")
    text = "\n".join(lines)
    await message.answer(text, reply_markup=_packages_keyboard().as_markup(), parse_mode="HTML")


@router.message(TextCmd(["купить зарники", "донат"]))
async def cmd_buy_zarniki(message: types.Message):
    await _send_packages_menu(message)


@router.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject, db, bot: Bot):
    if command.args == "buyzarniki":
        return await _send_packages_menu(message)

    # Growth-полиш 2026-07-13: /start ref<id> — реферальная ссылка.
    if command.args and command.args.startswith("ref") and command.args[3:].isdigit():
        referrer_id = int(command.args[3:])
        granted = await register_referral(db, message.from_user.id, referrer_id)
        if granted:
            bonus_line = (
                f"🪙 +{int(REFERRAL_SIGNUP_MORA)} Моры · 💎 +{int(REFERRAL_SIGNUP_DIAMONDS)} Алмазов · "
                f"👑 VIP на {REFERRAL_SIGNUP_VIP_DAYS} дн."
            )
            await message.answer(
                f"🎉 <b>Добро пожаловать по приглашению!</b>\n"
                f"Вам и другу, который вас позвал, начислено:\n{bonus_line}\n\n"
                f"Дальше — в группу, где стоит бот, и напишите «бот я», чтобы увидеть профиль.",
                parse_mode="HTML",
            )
            # DM рефереру может не дойти: та же ограниченность Bot API, что и в
            # продуктовой записке (находка 01) — бот не может писать тому, кто сам
            # не открывал с ним ЛС. Бонус уже начислен, уведомление best-effort.
            try:
                await bot.send_message(
                    referrer_id,
                    f"🎉 Ваш друг присоединился по вашей ссылке!\nВам начислено:\n{bonus_line}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return
        # Невалидная/повторная рефералка — не спамим ошибкой, просто обычное приветствие ниже.

    await message.answer(
        "👋 Привет! Я <b>Предвестник</b> — RPG-бот для групповых чатов.\n\n"
        "Команды пишутся словом «бот» прямо в сообщении группы "
        "(например «бот баланс», «бот помощь»).",
        parse_mode="HTML",
    )


@router.message(TextCmd(["рефералка", "пригласить друга", "реферальная ссылка"]))
async def cmd_referral_link(message: types.Message):
    """Growth-полиш 2026-07-13: личная ссылка-приглашение. Работает только в
    группе (как и остальные команды бота) — делиться ссылкой можно куда угодно."""
    link = f"https://t.me/{_BOT_USERNAME}?start=ref{message.from_user.id}"
    await message.answer(
        f"🤝 <b>Приведи друга — оба в плюсе!</b>\n\n"
        f"Как только друг перейдёт по ссылке и запустит бота — вам ОБОИМ:\n"
        f"🪙 +{int(REFERRAL_SIGNUP_MORA)} Моры · 💎 +{int(REFERRAL_SIGNUP_DIAMONDS)} Алмазов · "
        f"👑 VIP на {REFERRAL_SIGNUP_VIP_DAYS} дн.\n\n"
        f"А если друг потом купит ✨ Зарники — вам ещё бонус в Зарниках, с любой его покупки.\n\n"
        f"🔗 <code>{link}</code>",
        parse_mode="HTML",
    )


@router.callback_query(BuyZarnikiCB.filter())
async def cb_buy_package(query: types.CallbackQuery, callback_data: BuyZarnikiCB, bot: Bot):
    stars = callback_data.stars

    if stars == 0:
        await query.message.answer(
            f"{_CUSTOM_AMOUNT_MARKER}\n\n"
            f"Ответьте на это сообщение количеством ⭐ (от 1 до {_MAX_STARS})."
        )
        return await query.answer()

    # Ищем пакет — если нашли, начисляем base + bonus; иначе расчёт по тарифу
    pkg = next((p for p in STARS_PACKAGES if p[0] == stars), None)
    if pkg:
        zarniki = pkg[1] + pkg[2]  # base + bonus
    else:
        zarniki = stars * ZARNIKI_PER_STAR
    await bot.send_invoice(
        chat_id=query.from_user.id,
        title="Зарники ✨",
        description=f"{zarniki}✨ Зарников для Предвестника",
        payload=f"zarniki:{zarniki}",
        currency="XTR",
        prices=[LabeledPrice(label=f"{zarniki}✨ Зарников", amount=stars)],
    )
    await query.answer()


class _ZarnikiAmountReply(BaseFilter):
    """Реплай числом ⭐ на сообщение-маркер кастомной суммы.
    Возвращает False (passthrough) для любых других реплаев."""

    async def __call__(self, message: types.Message) -> bool:
        reply = message.reply_to_message
        if not reply or not reply.text or _CUSTOM_AMOUNT_MARKER not in reply.text:
            return False
        return bool(message.text and message.text.strip().isdigit())


@router.message(_ZarnikiAmountReply())
async def msg_custom_zarniki_amount(message: types.Message, bot: Bot):
    stars = int(message.text.strip())
    if not (1 <= stars <= _MAX_STARS):
        return await message.answer(f"⚠️ Введите число от 1 до {_MAX_STARS}.")

    zarniki = stars * ZARNIKI_PER_STAR
    await bot.send_invoice(
        chat_id=message.from_user.id,
        title="Зарники ✨",
        description=f"{zarniki}✨ Зарников для Предвестника",
        payload=f"zarniki:{zarniki}",
        currency="XTR",
        prices=[LabeledPrice(label=f"{zarniki}✨ Зарников", amount=stars)],
    )


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    pl = pre_checkout_query.invoice_payload
    if pl.startswith("zarniki:"):
        await pre_checkout_query.answer(ok=True)
    else:
        await pre_checkout_query.answer(ok=False, error_message="Неизвестный платёж.")


@router.message(F.successful_payment)
async def on_successful_payment(message: types.Message, db, bot: Bot):
    payload = message.successful_payment.invoice_payload

    if payload.startswith("zarniki:"):
        amount = int(payload.split(":")[1])
        await eco_db.add_balance(
            db, message.from_user.id, zarniki=amount, source="stars_purchase",
            note=f"{message.successful_payment.total_amount}⭐",
        )
        await message.answer(
            f"✅ Начислено <b>{amount}✨</b> Зарников! Спасибо за поддержку проекта 💜",
            parse_mode="HTML",
        )
        # Growth-полиш 2026-07-13: комиссия рефереру, если покупатель пришёл по рефералке.
        commission = await pay_purchase_commission(db, message.from_user.id, amount)
        if commission:
            referrer_id, bonus = commission
            try:
                await bot.send_message(
                    referrer_id,
                    f"✨ Ваш друг купил Зарники — вам начислено <b>+{bonus}✨</b> комиссии!",
                    parse_mode="HTML",
                )
            except Exception:
                pass


