# bot/handlers/vip.py
"""VIP-подписка: статус + покупка тарифов за ✨ Зарники (Implementation Block 2.4)."""
from aiogram import Router, types
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.registry import VIP_TIERS, ITEMS_REGISTRY
from services.vip import get_vip_info, purchase_vip

router = Router(name="vip_router")


class VipBuyCB(CallbackData, prefix="vipbuy"):
    tier: str


def _tiers_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for tier, info in VIP_TIERS.items():
        builder.button(
            text=f"Купить {info['label']} — {info['price_zarniki']}✨",
            callback_data=VipBuyCB(tier=tier),
        )
    builder.adjust(1)
    return builder


def _gift_text(gift: dict) -> str:
    parts = []
    if gift.get("mora", 0) > 0:
        parts.append(f"{gift['mora']:.0f} 🪙")
    if gift.get("diamonds", 0) > 0:
        parts.append(f"{gift['diamonds']:.0f} 💎")
    for item_id, qty in gift.get("items", ()):
        name = ITEMS_REGISTRY.get(item_id, {}).get("name", item_id)
        parts.append(f"{qty}× {name}")
    return ", ".join(parts)


def _tier_description(info: dict) -> str:
    weekly = ", ".join(
        f"{qty}× {ITEMS_REGISTRY.get(item_id, {}).get('name', item_id)}"
        for item_id, qty in info["weekly"]
    )
    lines = [
        f"<b>{info['label']}</b> — {info['price_zarniki']}✨ / {info['duration_days']} дн.",
        f"🎁 Подарок: {_gift_text(info['gift'])}",
        f"📅 Еженедельно: {weekly}",
    ]
    if info["extra_slot"]:
        lines.append("✅ +1 слот питомника")
    return "\n".join(lines)


@router.message(TextCmd(["vip", "вип"]))
async def cmd_vip(message: types.Message, db):
    user_id = message.from_user.id
    info = await get_vip_info(db, user_id)

    if info:
        header = (
            "👑 <b>VIP-СТАТУС</b>\n\n"
            f"Тариф: <b>{info['tier_label']}</b>\n"
            f"Истекает: {info['expires_at']:%d.%m.%Y} ({info['days_left']} дн.)\n\n"
            "Можно купить ещё тариф — срок сложится, тариф сменится сразу:\n"
        )
    else:
        header = (
            "👑 <b>VIP-ПОДПИСКА</b>\n\n"
            "Косметика, удобство и еженедельные бонусы — без преимущества в силе.\n\n"
            "Доступные тарифы:\n"
        )

    body = "\n\n".join(_tier_description(i) for i in VIP_TIERS.values())
    await message.answer(header + "\n" + body, reply_markup=_tiers_keyboard().as_markup(), parse_mode="HTML")


@router.callback_query(VipBuyCB.filter())
async def cb_vip_buy(query: types.CallbackQuery, callback_data: VipBuyCB, db):
    ok, msg = await purchase_vip(db, query.from_user.id, callback_data.tier, chat_id=query.message.chat.id)
    await query.message.answer(msg, parse_mode="HTML")
    await query.answer()
