"""Telegram archive access for the retired Dark Mora earn loop."""
from aiogram import Router, types
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.registry import SHADOW_RELICS
from infrastructure.repositories.dark_mora import get_dark_mora_balance
from infrastructure.repositories import shadow_merchant as sm_repo
from services.utils import format_currency


router = Router(name="dark_mora_router")


@router.message(TextCmd(["тёмная мора", "темная мора", "тмора", "dark mora", "баланс тморы"]))
async def cmd_dark_balance(message: types.Message, db):
    balance = await get_dark_mora_balance(db, message.from_user.id)
    await message.answer(
        f"🌑 <b>АРХИВ НОЧИ</b>\n\n"
        f"Сохранено: <code>{balance:.0f} 🌑</code>\n\n"
        "<i>Новых начислений нет. Остаток можно потратить только на уже выпущенные архивные предметы.</i>",
        parse_mode="HTML",
    )


@router.message(TextCmd(["контрабанда"]))
async def cmd_contrabanda(message: types.Message, db, text_args: str = None):
    del db, text_args
    await message.answer(
        "🌑 Контрабанда закрыта: она больше не забирает Мору и не создаёт отдельную валюту."
    )


@router.message(TextCmd(["ритуал", "культ бездны"]))
async def cmd_ritual(message: types.Message, db):
    del db
    await message.answer(
        "🌑 Ритуал закрыт: стрик, уровень и питомцы больше не создают отдельную валюту."
    )


@router.message(TextCmd(["слово"]))
async def cmd_shadow_word(message: types.Message, db, text_args: str = None):
    del db, text_args
    await message.answer(
        "🕴 Новые пророчества Торговца закрыты. Уже полученные права и предметы сохранены."
    )


class SRelicBuyCB(CallbackData, prefix="srelic"):
    relic_id: str


@router.message(TextCmd(["теневые реликвии", "теневая лавка", "теневая реликвия"]))
async def cmd_shadow_relics(message: types.Message, db):
    """Show already-issued archive purchase rights and owned relics."""
    uid = message.from_user.id
    owned = set(await sm_repo.owned_shadow_relics(db, uid))
    vouchers = await sm_repo.voucher_count(db, uid)
    balance = await get_dark_mora_balance(db, uid)

    lines = ["🕴 <b>АРХИВНАЯ ЛАВКА</b>", ""]
    for relic_id, relic in SHADOW_RELICS.items():
        mark = "✅ В коллекции" if relic_id in owned else f"{relic['price_dark']:.0f} 🌑"
        lines.append(f"{relic['name']} — {mark}")
        lines.append(f"   <i>{relic['desc']}</i>")
    lines += [
        "",
        f"🗝 Сохранённых прав покупки: <b>{vouchers}</b>",
        f"🌑 Архивный остаток: <b>{format_currency(balance)}</b>",
        "",
        "<i>Новые права здесь не выдаются; реликвии не дают боевую силу.</i>",
    ]

    keyboard = InlineKeyboardBuilder()
    if vouchers > 0:
        for relic_id, relic in SHADOW_RELICS.items():
            if relic_id not in owned:
                keyboard.button(
                    text=f"Купить {relic['name']}",
                    callback_data=SRelicBuyCB(relic_id=relic_id),
                )
        keyboard.adjust(1)
    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=keyboard.as_markup() if vouchers > 0 else None,
    )


@router.callback_query(SRelicBuyCB.filter())
async def cb_shadow_relic_buy(
    query: types.CallbackQuery,
    callback_data: SRelicBuyCB,
    db,
):
    ok, message = await sm_repo.buy_shadow_relic(
        db, query.from_user.id, callback_data.relic_id,
        idempotency_key=f"telegram:shadow-relic:{query.id}",
    )
    await db.commit()
    if ok:
        await query.answer("🗝 Куплено!", show_alert=False)
        await query.message.answer(f"🕴 {message}", parse_mode="HTML")
    else:
        await query.answer(message, show_alert=True)
