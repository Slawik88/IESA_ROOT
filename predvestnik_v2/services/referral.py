"""services/referral.py — реферальная программа (Growth-полиш 2026-07-13,
продуктовая записка «Рост: 9 → 20»). Без bot.*/FastAPI.* импортов.

Поток: друг открывает бота по ссылке t.me/<bot>?start=ref<id> → приватный /start
(bot/handlers/payments.py::cmd_start) вызывает register_referral() → обоим сразу
Мора+Алмазы+VIP. Дальше, когда рефери покупает Зарники за Stars
(bot/handlers/payments.py::on_successful_payment), рефереру идёт % от суммы —
pay_purchase_commission(), без ограничения по времени (комиссия «навсегда»,
как явно описал продюсер проекта — не наше решение сокращать её самовольно).
"""
from core.constants import (
    REFERRAL_SIGNUP_MORA, REFERRAL_SIGNUP_DIAMONDS, REFERRAL_SIGNUP_VIP_DAYS,
    REFERRAL_SIGNUP_VIP_TIER, REFERRAL_PURCHASE_COMMISSION_PCT,
)
from infrastructure.repositories.economy import add_balance
from services.vip import grant_vip_days


async def register_referral(db, new_user_id: int, referrer_id: int) -> bool:
    """Привязать нового игрока к рефереру и выдать сигнап-бонус ОБОИМ.

    Защищено: самоприглас (referrer_id == new_user_id) отклоняется; привязка —
    ровно один раз на игрока (атомарный WHERE referred_by IS NULL, тот же паттерн,
    что services/onboarding.py::grant_starter_kit); реферер должен реально
    существовать в users. Возвращает True только если бонус реально выдан."""
    if not referrer_id or referrer_id == new_user_id:
        return False

    # Строки может ещё не быть — это первый контакт нового игрока с ботом вообще,
    # до любого сообщения в группе (там же обычно и создаётся users-запись).
    await db.execute(
        "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (new_user_id,)
    )

    async with db.execute(
        "UPDATE users SET referred_by = ? "
        "WHERE user_tg_id = ? AND referred_by IS NULL RETURNING user_tg_id",
        (referrer_id, new_user_id),
    ) as c:
        if not await c.fetchone():
            return False

    async with db.execute(
        "SELECT 1 FROM users WHERE user_tg_id = ?", (referrer_id,),
    ) as c:
        if not await c.fetchone():
            return False

    for uid in (new_user_id, referrer_id):
        await add_balance(
            db, uid, mora=REFERRAL_SIGNUP_MORA, diamonds=REFERRAL_SIGNUP_DIAMONDS,
            source="referral_signup",
        )
        await grant_vip_days(db, uid, REFERRAL_SIGNUP_VIP_TIER, REFERRAL_SIGNUP_VIP_DAYS)

    return True


async def pay_purchase_commission(db, buyer_id: int, zarniki_amount: float) -> tuple[int, float] | None:
    """Рефереру buyer_id (если есть) — комиссия в Зарниках при покупке Звёздами.
    Возвращает (referrer_id, начисленная сумма) для уведомления, иначе None."""
    async with db.execute(
        "SELECT referred_by FROM users WHERE user_tg_id = ?", (buyer_id,),
    ) as c:
        row = await c.fetchone()
    referrer_id = row[0] if row else None
    if not referrer_id:
        return None

    bonus = round(zarniki_amount * REFERRAL_PURCHASE_COMMISSION_PCT, 2)
    if bonus <= 0:
        return None
    await add_balance(
        db, referrer_id, zarniki=bonus, source="referral_commission",
        note=f"friend bought {zarniki_amount}",
    )
    return referrer_id, bonus
