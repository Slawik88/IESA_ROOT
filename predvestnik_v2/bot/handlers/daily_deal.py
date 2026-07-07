# DEPRECATED — МЁРТВЫЙ КОД (БЛОК19 «Web First»): роутер этого файла НЕ зарегистрирован
# в bot/handlers/__init__.py::main_router — ни одна команда/кнопка отсюда не выполняется.
# Механика живёт в мини-аппе (FastAPI/), чат-алиасы ловит web_redirect.py.
# Файл оставлен как референс. НЕ подключать без ревизии: тексты/поля могли устареть.
from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timezone, timedelta

from bot.filters.text_commands import TextCmd
from core.registry import ITEMS_REGISTRY
from infrastructure.repositories.daily_deal import already_purchased
from services.daily_deal import ensure_deals_fresh, purchase_slot, period_key
from services.utils import check_callback_owner
from core.constants import DAILY_DEAL_ROTATION_HOURS

router = Router(name="daily_deal_router")
from bot.middlewares.module_check_mw import ModuleCheckMiddleware
router.message.middleware(ModuleCheckMiddleware("module_daily_deal"))


class DealCB(CallbackData, prefix="deal"):
    action: str   # "menu" | "buy" | "refresh"
    slot: int = 0
    user_id: int = 0


def _time_until_reset() -> str:
    now = datetime.now(timezone.utc)
    if now.hour < DAILY_DEAL_ROTATION_HOURS:
        nxt = now.replace(hour=DAILY_DEAL_ROTATION_HOURS, minute=0, second=0, microsecond=0)
    else:
        nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    delta = nxt - now
    h, rem = divmod(int(delta.total_seconds()), 3600)
    m = rem // 60
    return f"{h}ч {m}мин" if h > 0 else f"{m}мин"


def _item_display(item_id: str) -> str:
    return ITEMS_REGISTRY.get(item_id, {}).get("name", item_id)


async def _build_deal_menu(db, user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    deals = await ensure_deals_fresh(db)
    today = period_key()
    reset_in = _time_until_reset()

    lines = [
        "🛒 <b>АКЦИЯ ДНЯ</b>\n",
        f"└ Обновление через: <code>{reset_in}</code>\n",
    ]

    b = InlineKeyboardBuilder()
    for deal in deals:
        slot = deal["slot"]
        name = _item_display(deal["item_id"])
        qty = deal["quantity"]
        bought = await already_purchased(db, user_id, slot, today)

        if deal["price_diamonds"] > 0:
            price_str = f"{deal['price_diamonds']:.1f} 💎"
            price_str = price_str.replace(".0 ", " ")
        else:
            price_str = f"{int(deal['price_mora'])} 🪙"

        is_diamond_slot = deal["price_diamonds"] > 0
        slot_icon = "💎" if is_diamond_slot else "🛒"
        status_icon = "✅" if bought else slot_icon

        qty_str = f"×{qty}" if qty > 1 else ""
        lines.append(
            f"{'└' if slot == 7 else '├'} [{status_icon}] "
            f"<b>{name}</b>{f' {qty_str}' if qty_str else ''} — <code>{price_str}</code>"
            + (" <i>(куплено)</i>" if bought else "")
        )

        if not bought:
            b.button(
                text=f"{slot_icon} {name}{f' ×{qty}' if qty > 1 else ''} — {price_str}",
                callback_data=DealCB(action="buy", slot=slot),
            )

    b.button(text="🔄 Обновить", callback_data=DealCB(action="refresh"))
    b.adjust(1)

    return "\n".join(lines), b.as_markup()


@router.message(TextCmd(["акция", "акция дня", "магазин дня", "ежедневный магазин"]))
async def cmd_daily_deal(message: types.Message, db):
    if message.chat.type == "private":
        return
    text, kb = await _build_deal_menu(db, message.from_user.id)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(DealCB.filter(F.action == "menu"))
async def cb_deal_menu(query: types.CallbackQuery, callback_data: DealCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    text, kb = await _build_deal_menu(db, query.from_user.id)
    await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await query.answer()


@router.callback_query(DealCB.filter(F.action == "refresh"))
async def cb_deal_refresh(query: types.CallbackQuery, callback_data: DealCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    text, kb = await _build_deal_menu(db, query.from_user.id)
    try:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await query.answer("🔄 Обновлено!")


@router.callback_query(DealCB.filter(F.action == "buy"))
async def cb_deal_buy(query: types.CallbackQuery, callback_data: DealCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    ok, msg = await purchase_slot(db, query.from_user.id, callback_data.slot)

    if not ok:
        await query.answer(f"❌ {msg}", show_alert=True)
        return

    await query.answer("✅ Куплено!", show_alert=False)
    text, kb = await _build_deal_menu(db, query.from_user.id)
    try:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
