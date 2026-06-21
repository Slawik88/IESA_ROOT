"""
services/daily_deal.py
Business logic for the daily rotating shop (Акция дня).
No bot/django imports.
"""
import random
from datetime import datetime, timezone, timedelta

from core.constants import (
    DAILY_DEAL_DISCOUNT_RANGE, DAILY_DEAL_MIN_SLOTS, DAILY_DEAL_MAX_SLOTS,
    DAILY_DEAL_MAX_QTY, DAILY_DEAL_ROTATION_HOURS,
)
from core.registry import DAILY_DEAL_POOL_MORA, DAILY_DEAL_POOL_DIAMOND
from infrastructure.repositories import daily_deal as repo
from infrastructure.repositories import economy as eco_repo


def _get_today_utc() -> str:
    """Return current UTC date as 'YYYY-MM-DD'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def period_key() -> str:
    """Ключ текущего 12-часового периода: 'YYYY-MM-DD-A' (00-12 UTC) / '-B' (12-24).
    Используется и для свежести акций, и для дедупликации покупок (сброс каждые 12ч).
    Не валидная дата → pg_adapter не коэрсит в datetime, хранится как TEXT."""
    now = datetime.now(timezone.utc)
    half = "A" if now.hour < DAILY_DEAL_ROTATION_HOURS else "B"
    return f"{now.strftime('%Y-%m-%d')}-{half}"


def _seconds_until_reset() -> int:
    """Секунд до следующей ротации (ближайшая граница 00:00 или 12:00 UTC)."""
    now = datetime.now(timezone.utc)
    if now.hour < DAILY_DEAL_ROTATION_HOURS:
        nxt = now.replace(hour=DAILY_DEAL_ROTATION_HOURS, minute=0, second=0, microsecond=0)
    else:
        nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((nxt - now).total_seconds())


def _pick_unique_slots(pool: list, n: int) -> list[dict]:
    """Pick n distinct items from pool, no repeats on item_id."""
    shuffled = pool.copy()
    random.shuffle(shuffled)
    seen: set[str] = set()
    result = []
    for entry in shuffled:
        if entry["item_id"] not in seen:
            seen.add(entry["item_id"])
            result.append(entry)
        if len(result) == n:
            break
    # Fill remaining with repeats if pool is smaller than n
    if len(result) < n:
        for entry in pool:
            if len(result) >= n:
                break
            if entry not in result:
                result.append(entry)
    return result[:n]


def _clamped_qty(entry: dict) -> int:
    """Кол-во товара в слоте, зажатое в [1, DAILY_DEAL_MAX_QTY]."""
    qmin, qmax = entry["qty_range"]
    lo = max(1, min(qmin, DAILY_DEAL_MAX_QTY))
    hi = max(lo, min(qmax, DAILY_DEAL_MAX_QTY))
    return random.randint(lo, hi)


def generate_deal_slots() -> list[dict]:
    """Сгенерировать ротацию: 3-7 слотов, скидка 5-50% индивидуально на товар,
    кол-во 1-4 в слоте, смесь Мора/Алмазы. Returns list of slot dicts."""
    n = random.randint(DAILY_DEAL_MIN_SLOTS, DAILY_DEAL_MAX_SLOTS)
    n_dia = random.randint(0, min(len(DAILY_DEAL_POOL_DIAMOND), max(1, n // 3)))
    n_mora = n - n_dia
    slots: list[dict] = []
    slot_no = 1

    for entry in _pick_unique_slots(DAILY_DEAL_POOL_MORA, n_mora):
        qty = _clamped_qty(entry)
        discount = random.uniform(*DAILY_DEAL_DISCOUNT_RANGE)
        price = round(entry.get("base_price_mora", 0) * qty * (1.0 - discount))
        slots.append({"slot": slot_no, "item_id": entry["item_id"], "quantity": qty,
                      "price_mora": float(max(1, price)), "price_diamonds": 0.0})
        slot_no += 1

    for entry in _pick_unique_slots(DAILY_DEAL_POOL_DIAMOND, n_dia):
        qty = _clamped_qty(entry)
        discount = random.uniform(*DAILY_DEAL_DISCOUNT_RANGE)
        price = round(entry.get("base_price_dia", 0) * qty * (1.0 - discount), 1)
        slots.append({"slot": slot_no, "item_id": entry["item_id"], "quantity": qty,
                      "price_mora": 0.0, "price_diamonds": max(0.1, price)})
        slot_no += 1

    return slots


async def ensure_deals_fresh(db) -> list[dict]:
    """Вернуть текущие акции, перегенерировав при смене 12-часового периода."""
    key = period_key()
    gen_at = await repo.get_generated_at(db)

    if gen_at == key:
        return await repo.get_current_deals(db)

    slots = generate_deal_slots()
    await repo.save_deals(db, slots, key)
    return slots


async def purchase_slot(
    db,
    user_id: int,
    slot: int,
) -> tuple[bool, str]:
    """Attempt to purchase deal slot for the user today.
    Returns (True, success_msg) or (False, error_msg).
    """
    today = period_key()
    deals = await repo.get_current_deals(db)
    deal = next((d for d in deals if d["slot"] == slot), None)

    if not deal:
        return False, "Слот не найден. Попробуйте обновить акцию (/акция)."

    mora_cost = deal["price_mora"]
    dia_cost = deal["price_diamonds"]
    item_id = deal["item_id"]
    qty = deal["quantity"]

    try:
        await db.execute("BEGIN IMMEDIATE")
        # M7: лочим строку игрока — параллельные покупки разных слотов не уйдут в минус
        await db.execute("INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user_id,))
        async with db.execute("SELECT 1 FROM users WHERE user_tg_id = ? FOR UPDATE", (user_id,)) as _lk:
            await _lk.fetchone()

        # Check inside transaction to prevent double-purchase race condition
        if await repo.already_purchased(db, user_id, slot, today):
            await db.rollback()
            return False, "Вы уже купили этот слот сегодня."

        bal = await eco_repo.get_balance(db, user_id)
        if mora_cost > 0 and bal["user_balance_mora"] < mora_cost:
            await db.rollback()
            return False, f"Недостаточно Моры (нужно {mora_cost:.0f} 🪙)."
        if dia_cost > 0 and bal["user_balance_diamonds"] < dia_cost:
            await db.rollback()
            return False, f"Недостаточно Алмазов (нужно {dia_cost} 💎)."

        if mora_cost > 0:
            await eco_repo.add_balance(db, user_id, mora=-mora_cost, commit=False,
                                       source="daily_deal_purchase", note=f"{item_id}×{qty}")
        if dia_cost > 0:
            await eco_repo.add_balance(db, user_id, diamonds=-dia_cost, commit=False,
                                       source="daily_deal_purchase", note=f"{item_id}×{qty}")

        await db.execute(
            "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
            (user_id, item_id, qty, qty),
        )
        await repo.record_purchase(db, user_id, slot, today)
        await db.commit()

        return True, f"✅ Куплено: {qty}× {item_id}"

    except Exception as e:
        await db.rollback()
        return False, f"Ошибка: {e}"
