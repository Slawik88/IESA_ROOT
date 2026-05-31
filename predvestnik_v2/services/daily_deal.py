"""
services/daily_deal.py
Business logic for the daily rotating shop (Акция дня).
No bot/django imports.
"""
import random
from datetime import datetime, timezone, timedelta

from core.constants import DAILY_DEAL_DISCOUNT_RANGE, DAILY_DEAL_MORA_SLOTS
from core.registry import DAILY_DEAL_POOL_MORA, DAILY_DEAL_POOL_DIAMOND
from infrastructure.repositories import daily_deal as repo
from infrastructure.repositories import economy as eco_repo


def _get_today_utc() -> str:
    """Return current UTC date as 'YYYY-MM-DD'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _get_reset_timestamp() -> str:
    """Return 'YYYY-MM-DD' for today UTC.
    Date-only format avoids pg_adapter coercing the string to datetime
    when inserting into daily_deal_current.generated_at TEXT column."""
    return _get_today_utc()


def _seconds_until_midnight_utc() -> int:
    now = datetime.now(timezone.utc)
    next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((next_midnight - now).total_seconds())


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


def generate_deal_slots() -> list[dict]:
    """Generate a fresh set of 7 deal slots (6 mora + 1 diamond).
    Returns list of dicts: {slot, item_id, quantity, price_mora, price_diamonds}.
    """
    now_str = _get_reset_timestamp()
    slots: list[dict] = []

    mora_picks = _pick_unique_slots(DAILY_DEAL_POOL_MORA, DAILY_DEAL_MORA_SLOTS)
    for i, entry in enumerate(mora_picks, start=1):
        qty_min, qty_max = entry["qty_range"]
        qty = random.randint(qty_min, qty_max)
        base = entry.get("base_price_mora", 0)
        discount = random.uniform(*DAILY_DEAL_DISCOUNT_RANGE)
        price = round(base * qty * (1.0 - discount))
        slots.append({
            "slot": i,
            "item_id": entry["item_id"],
            "quantity": qty,
            "price_mora": float(max(1, price)),
            "price_diamonds": 0.0,
        })

    dia_pick = random.choice(DAILY_DEAL_POOL_DIAMOND)
    qty_min, qty_max = dia_pick["qty_range"]
    qty = random.randint(qty_min, qty_max)
    base_dia = dia_pick.get("base_price_dia", 0)
    discount = random.uniform(*DAILY_DEAL_DISCOUNT_RANGE)
    price_dia = round(base_dia * qty * (1.0 - discount), 1)
    slots.append({
        "slot": 7,
        "item_id": dia_pick["item_id"],
        "quantity": qty,
        "price_mora": 0.0,
        "price_diamonds": max(0.1, price_dia),
    })

    return slots


async def ensure_deals_fresh(db) -> list[dict]:
    """Return current deals, regenerating if they're stale (different UTC date)."""
    today = _get_today_utc()
    gen_at = await repo.get_generated_at(db)

    if gen_at and gen_at.startswith(today):
        return await repo.get_current_deals(db)

    slots = generate_deal_slots()
    await repo.save_deals(db, slots, _get_reset_timestamp())
    return slots


async def purchase_slot(
    db,
    user_id: int,
    slot: int,
) -> tuple[bool, str]:
    """Attempt to purchase deal slot for the user today.
    Returns (True, success_msg) or (False, error_msg).
    """
    today = _get_today_utc()
    deals = await repo.get_current_deals(db)
    deal = next((d for d in deals if d["slot"] == slot), None)

    if not deal:
        return False, "Слот не найден. Попробуйте обновить акцию (/акция)."

    if await repo.already_purchased(db, user_id, slot, today):
        return False, "Вы уже купили этот слот сегодня."

    mora_cost = deal["price_mora"]
    dia_cost = deal["price_diamonds"]
    item_id = deal["item_id"]
    qty = deal["quantity"]

    try:
        await db.execute("BEGIN IMMEDIATE")

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
