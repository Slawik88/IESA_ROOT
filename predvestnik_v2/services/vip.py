"""services/vip.py — VIP-подписка: статус, покупка, бонусы (Implementation Block 2.3).

Без bot.* / FastAPI.* импортов — общая логика для бота и мини-аппа.
"""
from datetime import datetime, timezone
import math

from core.registry import VIP_TIERS, ITEMS_REGISTRY
from infrastructure.repositories.economy import add_balance, add_item


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def is_vip_active(db, user_id: int) -> bool:
    async with db.execute(
        "SELECT 1 FROM vip_subscriptions WHERE user_id = ? AND expires_at > NOW()",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    return row is not None


async def get_vip_info(db, user_id: int) -> dict | None:
    """Возвращает {'tier','tier_label','expires_at','days_left'} либо None, если VIP не активен."""
    async with db.execute(
        "SELECT tier, expires_at FROM vip_subscriptions WHERE user_id = ? AND expires_at > NOW()",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    if not row:
        return None

    tier, expires_at = row[0], _aware(row[1])
    days_left = max(0, math.ceil((expires_at - datetime.now(timezone.utc)).total_seconds() / 86400))
    return {
        "tier": tier,
        "tier_label": VIP_TIERS.get(tier, {}).get("label", tier),
        "expires_at": expires_at,
        "days_left": days_left,
    }


async def get_extra_pet_slots(db, user_id: int) -> int:
    """0 или 1 — дополнительный слот питомника для тарифов с extra_slot=True (Блок 4)."""
    info = await get_vip_info(db, user_id)
    if info and VIP_TIERS.get(info["tier"], {}).get("extra_slot"):
        return 1
    return 0


async def get_vip_seniority_days(db, user_id: int) -> int:
    """«Стаж VIP» — суммарно оплаченных дней за всё время (включая истёкшие подписки)."""
    async with db.execute(
        "SELECT COALESCE(total_days, 0) FROM vip_subscriptions WHERE user_id = ?",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    return int(row[0]) if row else 0


async def purchase_vip(db, user_id: int, tier: str, chat_id: int | None = None,
                       target_user_id: int | None = None) -> tuple[bool, str]:
    """Покупка/продление/апгрейд VIP-подписки за ✨ Зарники.

    Длительность стекуется поверх остатка активной подписки, тариф меняется
    сразу, разовый подарок выдаётся при каждой покупке любого тарифа.

    target_user_id — «подарить вип»: платит user_id, подписку и подарок
    получает target_user_id. total_days (стаж) копится у получателя.
    """
    info = VIP_TIERS.get(tier)
    if not info:
        return False, "❌ Неизвестный тариф VIP."

    price = info["price_zarniki"]
    days = info["duration_days"]
    recipient = target_user_id or user_id

    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT COALESCE(user_balance_zarniki, 0) FROM users WHERE user_tg_id = ? FOR UPDATE",
                (user_id,),
            ) as c:
                row = await c.fetchone()
            current = float(row[0]) if row else 0.0
            if current < price:
                return False, f"❌ Недостаточно ✨ (нужно {price:.0f}, есть {current:.0f})."

            await add_balance(db, user_id, zarniki=-price, source="vip_purchase",
                               chat_id=chat_id, note=tier if recipient == user_id else f"{tier}_gift_to_{recipient}")

            await db.execute(
                "INSERT INTO vip_subscriptions (user_id, tier, started_at, expires_at, expiry_notified, total_days) "
                "VALUES (?, ?, NOW(), NOW() + make_interval(days => ?), FALSE, ?) "
                "ON CONFLICT (user_id) DO UPDATE SET "
                "tier = EXCLUDED.tier, "
                "started_at = CASE WHEN vip_subscriptions.expires_at > NOW() "
                "THEN vip_subscriptions.started_at ELSE NOW() END, "
                "expires_at = CASE WHEN vip_subscriptions.expires_at > NOW() "
                "THEN vip_subscriptions.expires_at + make_interval(days => ?) "
                "ELSE NOW() + make_interval(days => ?) END, "
                "expiry_notified = FALSE, "
                "total_days = COALESCE(vip_subscriptions.total_days, 0) + ?",
                (recipient, tier, days, days, days, days, days),
            )

            gift = info["gift"]
            granted = []
            if gift.get("mora", 0) > 0:
                await add_balance(db, recipient, mora=gift["mora"], source="vip_gift",
                                   chat_id=chat_id, note=tier)
                granted.append(f"+{gift['mora']:.0f} 🪙")
            if gift.get("diamonds", 0) > 0:
                await add_balance(db, recipient, diamonds=gift["diamonds"], source="vip_gift",
                                   chat_id=chat_id, note=tier)
                granted.append(f"+{gift['diamonds']:.0f} 💎")
            for item_id, qty in gift.get("items", ()):
                await add_item(db, recipient, item_id, qty)
                item_name = ITEMS_REGISTRY.get(item_id, {}).get("name", item_id)
                granted.append(f"+{qty}× {item_name}")

        gift_text = ", ".join(granted) if granted else "—"
        if recipient != user_id:
            return True, (
                f"🎁 Подарен <b>{info['label']}</b> на {days} дн.!\n"
                f"🎁 Бонус получателю: {gift_text}"
            )
        return True, (
            f"✅ Оформлен <b>{info['label']}</b> на {days} дн.!\n"
            f"🎁 Подарок: {gift_text}"
        )
    except Exception as e:
        return False, f"❌ Ошибка: {e}"
