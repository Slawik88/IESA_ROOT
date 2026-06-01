from datetime import datetime, timezone, timedelta

from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.constants import (
    EXCHANGE_RATE_MORA_PER_DIAMOND,
    EXCHANGE_DAILY_CAP_DIAMONDS,
    EXCHANGE_MIN_DIAMONDS_PER_REQUEST,
)
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories.exchange import (
    get_active_event, get_user_quota, add_quota,
)
from services.utils import format_currency, parse_dt, check_callback_owner

router = Router(name="exchange_router")
from bot.middlewares.module_check_mw import ModuleCheckMiddleware
router.message.middleware(ModuleCheckMiddleware("module_exchange"))


class ExchCB(CallbackData, prefix="exch"):
    action: str   # "menu" | "confirm"
    amount: float = 0.0
    user_id: int = 0


def _time_left(ends_at_str: str) -> str:
    try:
        ends = parse_dt(ends_at_str).replace(tzinfo=timezone.utc)
        delta = ends - datetime.now(timezone.utc)
        if delta.total_seconds() <= 0:
            return "завершён"
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m = rem // 60
        return f"{h}ч {m}м"
    except Exception:
        return "?"


async def _find_next_event_info(db) -> str:
    from infrastructure.repositories.exchange import get_scheduled_event
    ev = await get_scheduled_event(db)
    if ev:
        try:
            dt = parse_dt(ev["starts_at"]).replace(tzinfo=timezone.utc)
            delta = dt - datetime.now(timezone.utc)
            h, rem = divmod(int(max(0, delta.total_seconds())), 3600)
            d = h // 24
            h = h % 24
            return f"Следующий ивент через ~{d}д {h}ч" if d > 0 else f"Следующий ивент через ~{h}ч"
        except Exception:
            pass
    return "Следующий ивент не запланирован"


@router.message(TextCmd(["обмен", "конвертация", "обменять"]))
async def cmd_exchange(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return

    event = await get_active_event(db)
    if not event:
        next_info = await _find_next_event_info(db)
        return await message.answer(
            f"💱 <b>ОБМЕН МОРЫ → АЛМАЗЫ</b>\n\n"
            f"<i>Ивент сейчас неактивен.</i>\n"
            f"└ {next_info}",
            parse_mode="HTML",
        )

    user_id = message.from_user.id
    event_id = event["id"]
    used_quota = await get_user_quota(db, user_id, event_id)
    remaining_quota = EXCHANGE_DAILY_CAP_DIAMONDS - used_quota
    bal = await eco_repo.get_balance(db, user_id)

    # Text arg = diamonds to convert
    raw = (text_args or "").strip()
    if raw and raw.replace(".", "").isdigit():
        diamonds = float(raw)
        diamonds = max(EXCHANGE_MIN_DIAMONDS_PER_REQUEST, min(diamonds, remaining_quota))
        mora_cost = diamonds * EXCHANGE_RATE_MORA_PER_DIAMOND

        if diamonds < EXCHANGE_MIN_DIAMONDS_PER_REQUEST:
            return await message.answer(
                f"❌ Минимум <code>{int(EXCHANGE_MIN_DIAMONDS_PER_REQUEST)} 💎</code> за раз.",
                parse_mode="HTML",
            )
        if bal["user_balance_mora"] < mora_cost:
            return await message.answer(
                f"❌ Недостаточно Моры. Нужно: <code>{format_currency(mora_cost)} 🪙</code>.",
                parse_mode="HTML",
            )

        # Confirm button
        b = InlineKeyboardBuilder()
        b.button(text=f"✅ Обменять {int(diamonds)} 💎",
                 callback_data=ExchCB(action="confirm", amount=diamonds))
        b.button(text="❌ Отмена", callback_data=ExchCB(action="menu"))
        b.adjust(1)
        await message.answer(
            f"💱 <b>ПОДТВЕРЖДЕНИЕ ОБМЕНА</b>\n\n"
            f"├ Отдаёте: <code>{format_currency(mora_cost)} 🪙</code>\n"
            f"└ Получаете: <code>{int(diamonds)} 💎</code>",
            reply_markup=b.as_markup(),
            parse_mode="HTML",
        )
        return

    # Show exchange menu
    b = InlineKeyboardBuilder()
    for diamonds in [5, 10, 25, 50, 100]:
        if diamonds <= remaining_quota and diamonds * EXCHANGE_RATE_MORA_PER_DIAMOND <= bal["user_balance_mora"]:
            b.button(text=f"{diamonds} 💎  ({int(diamonds * EXCHANGE_RATE_MORA_PER_DIAMOND):,} 🪙)",
                     callback_data=ExchCB(action="confirm", amount=float(diamonds)))
    b.adjust(2)

    await message.answer(
        f"💱 <b>ОБМЕН МОРЫ → АЛМАЗЫ</b>\n\n"
        f"├ Курс: <code>{int(EXCHANGE_RATE_MORA_PER_DIAMOND)} 🪙 = 1 💎</code>\n"
        f"├ Лимит сегодня: <code>{int(remaining_quota)}/{int(EXCHANGE_DAILY_CAP_DIAMONDS)} 💎</code>\n"
        f"├ ⏳ Осталось: <b>{_time_left(event['ends_at'])}</b>\n"
        f"└ Ваш баланс: <code>{format_currency(bal['user_balance_mora'])} 🪙</code>\n\n"
        f"<i>Быстрый обмен:</i>",
        reply_markup=b.as_markup() if b._buttons else None,
        parse_mode="HTML",
    )


@router.callback_query(ExchCB.filter(F.action == "menu"))
async def cb_exchange_menu(query: types.CallbackQuery, callback_data: ExchCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    await query.answer()
    await cmd_exchange(query.message, db)


@router.callback_query(ExchCB.filter(F.action == "confirm"))
async def cb_exchange_confirm(query: types.CallbackQuery, callback_data: ExchCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    diamonds = callback_data.amount
    user_id = query.from_user.id

    event = await get_active_event(db)
    if not event:
        await query.answer("❌ Ивент уже завершён!", show_alert=True)
        return

    event_id = event["id"]
    used_quota = await get_user_quota(db, user_id, event_id)
    remaining = EXCHANGE_DAILY_CAP_DIAMONDS - used_quota

    if diamonds > remaining:
        await query.answer(f"❌ Квота исчерпана. Осталось: {int(remaining)} 💎.", show_alert=True)
        return

    mora_cost = diamonds * EXCHANGE_RATE_MORA_PER_DIAMOND
    bal = await eco_repo.get_balance(db, user_id)
    if bal["user_balance_mora"] < mora_cost:
        await query.answer("❌ Недостаточно Моры.", show_alert=True)
        return

    await eco_repo.add_balance(db, user_id, mora=-mora_cost, diamonds=diamonds,
                               source="exchange_mora_to_dia",
                               chat_id=query.message.chat.id,
                               note=f"{int(diamonds)}dia")
    await add_quota(db, user_id, event_id, diamonds)
    await db.commit()

    await query.answer(f"✅ +{int(diamonds)} 💎 (−{format_currency(mora_cost)} 🪙)", show_alert=False)
    await query.message.edit_text(
        f"✅ <b>Обмен успешен!</b>\n\n"
        f"├ Потрачено: <code>{format_currency(mora_cost)} 🪙</code>\n"
        f"└ Получено: <code>{int(diamonds)} 💎</code>",
        parse_mode="HTML",
    )
