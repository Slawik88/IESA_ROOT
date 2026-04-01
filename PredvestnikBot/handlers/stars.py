"""
Telegram Stars — покупка кристаллов 💎.

Команды:
  бот кристаллы / бот купить кристаллы  — меню покупки кристаллов
  бот мои кристаллы / бот баланс кристаллов — показать баланс

PreCheckoutQuery + SuccessfulPayment обрабатываются автоматически.
"""

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    CallbackQuery,
)

from database.db import add_crystals, get_crystals, log_stars_purchase
from filters.bot_command import BotCommand
from shared_prices import CRYSTAL_PACKS

from filters.chat_mode import MainChatOnly
router = Router()
router.message.filter(MainChatOnly())
router.callback_query.filter(MainChatOnly())


log = logging.getLogger(__name__)


# ─── Deep-link: /start buycrystals_PACK ──────────────────────────────────────

@router.message(CommandStart(deep_link=True, deep_link_encoded=False), F.chat.type == "private")
async def cmd_start_buy_crystals(msg: Message):
    """Handle /start buycrystals_{pack_key} deep link from Mini App."""
    payload = msg.text.split(maxsplit=1)[1] if msg.text and " " in msg.text else ""
    if not payload.startswith("buycrystals_"):
        return  # let dm_roles handle other /start payloads

    pack_key = payload[len("buycrystals_"):]
    pack = CRYSTAL_PACKS.get(pack_key)
    if not pack:
        await msg.answer("❌ Пакет не найден. Используй /кристаллы для выбора.")
        return

    await msg.answer_invoice(
        title=f"{pack['label']} — {pack['crystals']} 💎",
        description=(
            f"Пополнение кристаллов Предвестника.\n"
            f"Вы получите: {pack['crystals']} 💎"
            + (f" (+{pack['bonus_pct']}% бонус)" if pack["bonus_pct"] else "")
        ),
        payload=f"crystals:{pack_key}:{msg.from_user.id}",
        currency="XTR",
        prices=[LabeledPrice(label=f"{pack['crystals']} 💎", amount=pack["stars"])],
        provider_token="",
        start_parameter=f"buy_{pack_key}",
    )

# ─── Клавиатура выбора пакета ────────────────────────────────────────────────

def _pack_keyboard(uid: int) -> InlineKeyboardMarkup:
    rows = []
    for pack_key, pack in CRYSTAL_PACKS.items():
        bonus = f"  (+{pack['bonus_pct']}% бонус)" if pack["bonus_pct"] else ""
        rows.append([
            InlineKeyboardButton(
                text=f"{pack['label']} — {pack['stars']} ⭐ → {pack['crystals']} 💎{bonus}",
                callback_data=f"stars_buy:{uid}:{pack_key}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="❌ Закрыть", callback_data=f"stars_close:{uid}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Команда: показать меню покупки ──────────────────────────────────────────

@router.message(BotCommand("кристаллы"))
@router.message(BotCommand("купить кристаллы"))
@router.message(BotCommand("crystals"))
async def cmd_crystals_shop(msg: Message):
    balance = await get_crystals(msg.from_user.id)
    text = (
        f"<b>💎 Кристаллы Предвестника</b>\n\n"
        f"Ваш текущий баланс: <b>{balance} 💎</b>\n\n"
        f"Кристаллы — премиум-валюта, которую можно использовать для покупки "
        f"эксклюзивной косметики в Mini App:\n"
        f"  • Уникальные рамки профиля 🖼\n"
        f"  • Аура и эффекты ✨\n"
        f"  • VIP на 7 дней 👑\n"
        f"  • Кристальный облик питомца 🐾\n\n"
        f"<b>Выберите пакет:</b>"
    )
    await msg.answer(text, reply_markup=_pack_keyboard(msg.from_user.id))


@router.message(BotCommand("мои кристаллы"))
@router.message(BotCommand("баланс кристаллов"))
async def cmd_crystal_balance(msg: Message):
    balance = await get_crystals(msg.from_user.id)
    await msg.answer(
        f"💎 Ваш баланс кристаллов: <b>{balance} 💎</b>\n"
        f"Купить больше: /кристаллы"
    )


# ─── Callback: закрыть меню ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("stars_close:"))
async def cb_stars_close(cb: CallbackQuery):
    _, uid = cb.data.split(":")
    if cb.from_user.id != int(uid):
        await cb.answer("Это не ваше меню.", show_alert=True)
        return
    await cb.message.delete()
    await cb.answer()


# ─── Callback: отправить инвойс за выбранный пакет ───────────────────────────

@router.callback_query(F.data.startswith("stars_buy:"))
async def cb_stars_buy(cb: CallbackQuery):
    parts = cb.data.split(":")
    if len(parts) != 3:
        await cb.answer("Некорректные данные.", show_alert=True)
        return
    _, uid, pack_key = parts
    if cb.from_user.id != int(uid):
        await cb.answer("Это не ваше меню.", show_alert=True)
        return

    pack = CRYSTAL_PACKS.get(pack_key)
    if not pack:
        await cb.answer("Пакет не найден.", show_alert=True)
        return

    await cb.answer()
    await cb.message.answer_invoice(
        title=f"{pack['label']} — {pack['crystals']} 💎",
        description=(
            f"Пополнение кристаллов Предвестника.\n"
            f"Вы получите: {pack['crystals']} 💎"
            + (f" (+{pack['bonus_pct']}% бонус)" if pack["bonus_pct"] else "")
        ),
        payload=f"crystals:{pack_key}:{cb.from_user.id}",
        currency="XTR",                    # Telegram Stars
        prices=[LabeledPrice(label=f"{pack['crystals']} 💎", amount=pack["stars"])],
        provider_token="",                  # Telegram Stars не требует токена провайдера
        start_parameter=f"buy_{pack_key}",
    )


# ─── PreCheckoutQuery: одобряем все платежи ──────────────────────────────────

@router.pre_checkout_query()
async def pre_checkout(pq: PreCheckoutQuery):
    # Проверяем что payload содержит правильный формат
    parts = pq.invoice_payload.split(":")
    if len(parts) == 3 and parts[0] == "crystals" and parts[1] in CRYSTAL_PACKS:
        await pq.answer(ok=True)
    else:
        await pq.answer(ok=False, error_message="Неверные данные платежа.")


# ─── SuccessfulPayment: начисляем кристаллы ──────────────────────────────────

@router.message(F.successful_payment)
async def successful_payment(msg: Message):
    sp = msg.successful_payment
    payload = sp.invoice_payload  # "crystals:{pack_key}:{user_id}"
    parts = payload.split(":")
    if len(parts) != 3 or parts[0] != "crystals":
        log.warning("Unknown Stars payment payload: %s", payload)
        return

    pack_key = parts[1]
    pack = CRYSTAL_PACKS.get(pack_key)
    if not pack:
        log.warning("Stars payment: unknown pack_key %s", pack_key)
        return

    user_id = msg.from_user.id
    crystals = pack["crystals"]
    stars = pack["stars"]
    charge_id = sp.telegram_payment_charge_id or ""

    new_balance = await add_crystals(user_id, crystals)
    await log_stars_purchase(user_id, stars, crystals, pack_key, charge_id)

    await msg.answer(
        f"✅ <b>Оплата прошла успешно!</b>\n\n"
        f"⭐ Потрачено: <b>{stars} Stars</b>\n"
        f"💎 Начислено: <b>{crystals} кристаллов</b>\n"
        f"💎 Баланс: <b>{new_balance}</b>\n\n"
        f"Тратьте кристаллы в Mini App → Магазин → Кристаллы."
    )
    log.info(
        "Stars purchase: user=%s pack=%s stars=%s crystals=%s charge=%s",
        user_id, pack_key, stars, crystals, charge_id,
    )
