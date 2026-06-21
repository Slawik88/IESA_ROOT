from datetime import date

from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.constants import (
    EXCHANGE_RATE_MORA_PER_DIAMOND,
    EXCHANGE_RATE_MORA_PER_DIAMOND_SELL,
    EXCHANGE_DAILY_CAP_DIAMONDS,
    EXCHANGE_SELL_DAILY_CAP_DIAMONDS,
    EXCHANGE_MIN_DIAMONDS_PER_REQUEST,
)
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories.exchange import get_user_quota, add_quota
from services import global_moderation
from services.utils import format_currency, check_callback_owner

router = Router(name="exchange_router")
from bot.middlewares.module_check_mw import ModuleCheckMiddleware
router.message.middleware(ModuleCheckMiddleware("module_exchange"))


# БЛОК 2.2: обмен Моры↔Алмазов теперь ПОСТОЯННЫЙ и ДВУСТОРОННИЙ (как в вебе,
# FastAPI/routers/exchange.py). Квота — дневная: ключ user_exchange_quota.event_id =
# YYYYMMDD (покупка) / -YYYYMMDD (продажа). Новый день = авто-сброс лимита.
class ExchCB(CallbackData, prefix="exch"):
    action: str   # "menu" | "buy" | "sell"
    amount: float = 0.0
    user_id: int = 0


def _buy_key() -> int:
    return int(date.today().strftime("%Y%m%d"))


def _sell_key() -> int:
    return -_buy_key()


async def _render_menu(db, user_id: int) -> tuple[str, InlineKeyboardBuilder]:
    bought = await get_user_quota(db, user_id, _buy_key())
    sold = await get_user_quota(db, user_id, _sell_key())
    buy_left = EXCHANGE_DAILY_CAP_DIAMONDS - bought
    sell_left = EXCHANGE_SELL_DAILY_CAP_DIAMONDS - sold
    bal = await eco_repo.get_balance(db, user_id)
    mora = bal["user_balance_mora"]
    dia = bal["user_balance_diamonds"]

    b = InlineKeyboardBuilder()
    for d in (5, 10, 25, 50, 100):
        if d <= buy_left and d * EXCHANGE_RATE_MORA_PER_DIAMOND <= mora:
            b.button(text=f"🛒 {d}💎 (−{int(d * EXCHANGE_RATE_MORA_PER_DIAMOND):,}🪙)",
                     callback_data=ExchCB(action="buy", amount=float(d), user_id=user_id))
    for d in (5, 10, 25, 50):
        if d <= sell_left and d <= dia:
            b.button(text=f"💸 {d}💎 (+{int(d * EXCHANGE_RATE_MORA_PER_DIAMOND_SELL):,}🪙)",
                     callback_data=ExchCB(action="sell", amount=float(d), user_id=user_id))
    b.adjust(2)

    text = (
        f"💱 <b>ОБМЕННИК ВАЛЮТ</b>\n\n"
        f"├ 🛒 Покупка: <code>{int(EXCHANGE_RATE_MORA_PER_DIAMOND)} 🪙 = 1 💎</code>\n"
        f"├ 💸 Продажа: <code>1 💎 = {int(EXCHANGE_RATE_MORA_PER_DIAMOND_SELL)} 🪙</code>\n"
        f"├ Лимит покупки: <code>{int(buy_left)}/{int(EXCHANGE_DAILY_CAP_DIAMONDS)} 💎</code>\n"
        f"├ Лимит продажи: <code>{int(sell_left)}/{int(EXCHANGE_SELL_DAILY_CAP_DIAMONDS)} 💎</code>\n"
        f"└ Баланс: <code>{format_currency(mora)} 🪙 · {dia:.1f} 💎</code>\n\n"
        f"<i>Продажа дешевле покупки (спред) — 💎 остаётся премиум-валютой.\n"
        f"Быстрый ввод: <code>обмен 25</code> (покупка).</i>"
    )
    return text, b


@router.message(TextCmd(["обмен", "конвертация", "обменять"]))
async def cmd_exchange(message: types.Message, db, text_args: str = None,
                       user_restricted: dict | None = None, chat_restricted: dict | None = None):
    if message.chat.type == "private":
        return
    restriction = user_restricted or chat_restricted
    if restriction:
        return await message.answer(global_moderation.restriction_message(restriction))

    user_id = message.from_user.id

    # Быстрый текстовый обмен — покупка: "обмен 25"
    raw = (text_args or "").strip()
    if raw and raw.replace(".", "").isdigit():
        diamonds = float(raw)
        if diamonds < EXCHANGE_MIN_DIAMONDS_PER_REQUEST:
            return await message.answer(
                f"❌ Минимум <code>{int(EXCHANGE_MIN_DIAMONDS_PER_REQUEST)} 💎</code> за раз.",
                parse_mode="HTML",
            )
        mora_cost = diamonds * EXCHANGE_RATE_MORA_PER_DIAMOND
        bal = await eco_repo.get_balance(db, user_id)
        if bal["user_balance_mora"] < mora_cost:
            return await message.answer(
                f"❌ Недостаточно Моры. Нужно: <code>{format_currency(mora_cost)} 🪙</code>.",
                parse_mode="HTML",
            )
        b = InlineKeyboardBuilder()
        b.button(text=f"✅ Купить {int(diamonds)} 💎",
                 callback_data=ExchCB(action="buy", amount=diamonds, user_id=user_id))
        b.button(text="❌ Отмена", callback_data=ExchCB(action="menu", user_id=user_id))
        b.adjust(1)
        return await message.answer(
            f"💱 <b>ПОДТВЕРЖДЕНИЕ ПОКУПКИ</b>\n\n"
            f"├ Отдаёте: <code>{format_currency(mora_cost)} 🪙</code>\n"
            f"└ Получаете: <code>{int(diamonds)} 💎</code>",
            reply_markup=b.as_markup(), parse_mode="HTML",
        )

    text, b = await _render_menu(db, user_id)
    await message.answer(
        text, reply_markup=b.as_markup() if b._buttons else None, parse_mode="HTML")


@router.callback_query(ExchCB.filter(F.action == "menu"))
async def cb_exchange_menu(query: types.CallbackQuery, callback_data: ExchCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    await query.answer()
    text, b = await _render_menu(db, query.from_user.id)
    await query.message.edit_text(
        text, reply_markup=b.as_markup() if b._buttons else None, parse_mode="HTML")


@router.callback_query(ExchCB.filter(F.action == "buy"))
async def cb_exchange_buy(query: types.CallbackQuery, callback_data: ExchCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    diamonds = callback_data.amount
    user_id = query.from_user.id
    if diamonds < EXCHANGE_MIN_DIAMONDS_PER_REQUEST:
        return await query.answer(f"❌ Минимум {int(EXCHANGE_MIN_DIAMONDS_PER_REQUEST)} 💎.", show_alert=True)

    key = _buy_key()
    mora_cost = diamonds * EXCHANGE_RATE_MORA_PER_DIAMOND
    err = None
    # atomic: лочим строку игрока на проверку+списание (без Telegram-IO внутри)
    async with eco_repo.atomic(db, user_id):
        used = await get_user_quota(db, user_id, key)
        bal = await eco_repo.get_balance(db, user_id)
        if diamonds > EXCHANGE_DAILY_CAP_DIAMONDS - used:
            err = f"❌ Лимит покупки исчерпан. Осталось: {int(EXCHANGE_DAILY_CAP_DIAMONDS - used)} 💎."
        elif bal["user_balance_mora"] < mora_cost:
            err = "❌ Недостаточно Моры."
        else:
            await eco_repo.add_balance(db, user_id, mora=-mora_cost, diamonds=diamonds,
                                       source="exchange_mora_to_dia",
                                       chat_id=query.message.chat.id, note=f"{int(diamonds)}dia")
            await add_quota(db, user_id, key, diamonds)
    if err:
        return await query.answer(err, show_alert=True)
    await query.answer(f"✅ +{int(diamonds)} 💎", show_alert=False)
    await query.message.edit_text(
        f"✅ <b>Покупка успешна!</b>\n\n"
        f"├ Потрачено: <code>{format_currency(mora_cost)} 🪙</code>\n"
        f"└ Получено: <code>{int(diamonds)} 💎</code>",
        parse_mode="HTML",
    )


@router.callback_query(ExchCB.filter(F.action == "sell"))
async def cb_exchange_sell(query: types.CallbackQuery, callback_data: ExchCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    diamonds = callback_data.amount
    user_id = query.from_user.id
    if diamonds < EXCHANGE_MIN_DIAMONDS_PER_REQUEST:
        return await query.answer(f"❌ Минимум {int(EXCHANGE_MIN_DIAMONDS_PER_REQUEST)} 💎.", show_alert=True)

    key = _sell_key()
    mora_gain = diamonds * EXCHANGE_RATE_MORA_PER_DIAMOND_SELL
    err = None
    async with eco_repo.atomic(db, user_id):
        used = await get_user_quota(db, user_id, key)
        bal = await eco_repo.get_balance(db, user_id)
        if diamonds > EXCHANGE_SELL_DAILY_CAP_DIAMONDS - used:
            err = f"❌ Лимит продажи исчерпан. Осталось: {int(EXCHANGE_SELL_DAILY_CAP_DIAMONDS - used)} 💎."
        elif bal["user_balance_diamonds"] < diamonds:
            err = "❌ Недостаточно Алмазов."
        else:
            await eco_repo.add_balance(db, user_id, mora=mora_gain, diamonds=-diamonds,
                                       source="exchange_dia_to_mora",
                                       chat_id=query.message.chat.id, note=f"{int(diamonds)}dia")
            await add_quota(db, user_id, key, diamonds)
    if err:
        return await query.answer(err, show_alert=True)
    await query.answer(f"✅ +{format_currency(mora_gain)} 🪙", show_alert=False)
    await query.message.edit_text(
        f"✅ <b>Продажа успешна!</b>\n\n"
        f"├ Продано: <code>{int(diamonds)} 💎</code>\n"
        f"└ Получено: <code>{format_currency(mora_gain)} 🪙</code>",
        parse_mode="HTML",
    )
