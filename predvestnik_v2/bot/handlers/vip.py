# bot/handlers/vip.py
"""VIP-подписка: статус + покупка тарифов за ✨ Зарники (Implementation Block 2.4).
+ «подарить вип @user» — виральная раздача VIP другому игроку за ✨ дарителя."""
from aiogram import Router, types
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.registry import VIP_TIERS, VIP_PERKS_PITCH, ITEMS_REGISTRY
from services.utils import resolve_target, safe_html
from services.vip import get_vip_info, get_vip_seniority_days, purchase_vip

router = Router(name="vip_router")


class VipBuyCB(CallbackData, prefix="vipbuy"):
    tier: str


class VipGiftCB(CallbackData, prefix="vipgift"):
    tier: str
    target_id: int
    buyer_id: int


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
    savings = info.get("base_price_zarniki", info["price_zarniki"]) - info["price_zarniki"]
    price_line = f"<b>{info['label']}</b> — {info['price_zarniki']}✨ / {info['duration_days']} дн."
    if savings > 0:
        price_line += f"  <s>{info['base_price_zarniki']}✨</s> <i>(−{savings}✨)</i>"
    lines = [price_line]
    if info.get("tagline"):
        lines.append(f"<i>{info['tagline']}</i>")
    lines.append(f"🎁 Сразу: {_gift_text(info['gift'])}")
    lines.append(f"📅 Каждую неделю: {weekly}")
    extra = info.get("extra_slots", 0)
    if extra:
        lines.append(f"🐾 +{extra} слот{'а' if extra > 1 else ''} питомника")
    return "\n".join(lines)


@router.message(TextCmd(["vip", "вип"]))
async def cmd_vip(message: types.Message, db):
    user_id = message.from_user.id
    info = await get_vip_info(db, user_id)
    seniority = await get_vip_seniority_days(db, user_id)
    seniority_line = (
        f"🏅 Стаж VIP: <b>{seniority // 30} мес.</b> ({seniority} дн.)\n" if seniority > 0 else ""
    )

    if info:
        header = (
            "👑 <b>VIP-СТАТУС</b>\n\n"
            f"Тариф: <b>{info['tier_label']}</b>\n"
            f"Истекает: {info['expires_at']:%d.%m.%Y} ({info['days_left']} дн.)\n"
            f"{seniority_line}\n"
            "Можно купить ещё тариф — срок сложится, тариф сменится сразу:\n"
        )
    else:
        perks = "\n".join(VIP_PERKS_PITCH)
        header = (
            "👑 <b>VIP-ПОДПИСКА</b>\n\n"
            f"{seniority_line}"
            "Только косметика, удобство и бонусы — <b>без преимущества в силе</b>. "
            "Что получаешь:\n\n"
            f"{perks}\n\n"
            "Выбери тариф:\n"
        )

    body = "\n\n".join(_tier_description(i) for i in VIP_TIERS.values())
    await message.answer(header + "\n" + body, reply_markup=_tiers_keyboard().as_markup(), parse_mode="HTML")


@router.callback_query(VipBuyCB.filter())
async def cb_vip_buy(query: types.CallbackQuery, callback_data: VipBuyCB, db):
    ok, msg = await purchase_vip(db, query.from_user.id, callback_data.tier, chat_id=query.message.chat.id)
    await query.message.answer(msg, parse_mode="HTML")
    await query.answer()


# ── «подарить вип @user» — платит даритель, получает цель ────────────────────────

@router.message(TextCmd(["подарить вип", "подарить vip", "вип в подарок"]))
async def cmd_gift_vip(message: types.Message, db, text_args: str = None):
    target_id, target_name, _ = await resolve_target(message, db, text_args)
    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот подарить вип, @юзер</code>\n"
            "Или ответьте на сообщение пользователя.",
            parse_mode="HTML",
        )
    if target_id == message.from_user.id:
        return await message.answer(
            "🤨 Подарить VIP самому себе нельзя — просто купи его: «бот вип».",
            parse_mode="HTML",
        )

    builder = InlineKeyboardBuilder()
    for tier, info in VIP_TIERS.items():
        builder.button(
            text=f"🎁 {info['label']} — {info['price_zarniki']}✨",
            callback_data=VipGiftCB(tier=tier, target_id=target_id,
                                    buyer_id=message.from_user.id),
        )
    builder.adjust(1)
    await message.answer(
        f"🎁 <b>VIP В ПОДАРОК</b>\n\n"
        f"Получатель: <b>{safe_html(target_name)}</b>\n"
        f"Зарники спишутся с вашего баланса. Выберите тариф:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(VipGiftCB.filter())
async def cb_vip_gift(query: types.CallbackQuery, callback_data: VipGiftCB, db, bot):
    if query.from_user.id != callback_data.buyer_id:
        return await query.answer("Это меню дарителя — не для вас 😉", show_alert=True)

    ok, msg = await purchase_vip(
        db, callback_data.buyer_id, callback_data.tier,
        chat_id=query.message.chat.id, target_user_id=callback_data.target_id,
    )
    if ok:
        label = VIP_TIERS.get(callback_data.tier, {}).get("label", callback_data.tier)
        await query.message.answer(
            f"🎉 <a href=\"tg://user?id={callback_data.buyer_id}\">Даритель</a> вручил "
            f"<a href=\"tg://user?id={callback_data.target_id}\">получателю</a> "
            f"подписку <b>{label}</b>! 👑\n{msg}",
            parse_mode="HTML",
        )
        try:
            await bot.send_message(
                callback_data.target_id,
                f"🎁 Вам подарили <b>{label}</b>! Загляни: «бот вип».",
                parse_mode="HTML",
            )
        except Exception:
            pass
    else:
        await query.message.answer(msg, parse_mode="HTML")
    await query.answer()
