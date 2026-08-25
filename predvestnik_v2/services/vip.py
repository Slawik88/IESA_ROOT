"""services/vip.py — VIP-подписка: статус, покупка, бонусы (Implementation Block 2.3).

Без bot.* / FastAPI.* импортов — общая логика для бота и мини-аппа.
"""
from datetime import datetime, timezone
import math

from core.registry import VIP_TIERS
from infrastructure.repositories.economy import add_balance


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def grant_vip_days(db, user_id: int, tier: str, days: int) -> None:
    """Выдать VIP БЕСПЛАТНО (без списания Зарников), стекуя поверх остатка
    активной подписки — та же формула, что в dev_console/vip.py::dev_give_vip
    и Growth-полиш 2026-07-13 (реф-бонус). Единый источник, чтобы обе выдачи
    не разъезжались по формуле стекинга."""
    await db.execute(
        "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user_id,))
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
        (user_id, tier, days, days, days, days, days),
    )


async def is_vip_active(db, user_id: int) -> bool:
    async with db.execute(
        "SELECT 1 FROM vip_subscriptions WHERE user_id = ? AND expires_at > NOW()",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    return row is not None


async def is_vip_active_batch(db, user_ids: list[int]) -> set[int]:
    """Множество user_id с активной VIP из списка — один запрос вместо N
    (используется при гейте VIP-косметики в массовых выборках: топы/клан)."""
    ids = [int(u) for u in (user_ids or [])]
    if not ids:
        return set()
    ph = ",".join(["?"] * len(ids))
    async with db.execute(
        f"SELECT user_id FROM vip_subscriptions "
        f"WHERE user_id IN ({ph}) AND expires_at > NOW()",
        tuple(ids),
    ) as c:
        rows = await c.fetchall()
    return {int(r[0]) for r in rows}


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
    """VIP v3 never changes companion capacity or gameplay output."""
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
    сразу. VIP v3 даёт только сервис и оформление — без валюты, предметов,
    попыток, игровых слотов и множителей.

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

        if recipient != user_id:
            return True, (
                f"🎁 Подарен <b>{info['label']}</b> на {days} дн.!\n"
                "Доступны оформление, история и сервис — без игрового преимущества."
            )
        return True, (
            f"✅ Оформлен <b>{info['label']}</b> на {days} дн.!\n"
            "Доступны оформление, история и сервис — без игрового преимущества."
        )
    except Exception as e:
        return False, f"❌ Ошибка: {e}"
