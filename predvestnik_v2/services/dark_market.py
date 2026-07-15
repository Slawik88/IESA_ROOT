"""
services/dark_market.py — Чёрный Рынок (R8): 3 товара за 🌑 Тёмную Мору,
ротация раз в ISO-неделю. Бизнес-логика общая для бота и сайта.
Без импортов bot.* / FastAPI.*.
"""
import random
from datetime import datetime, timedelta, timezone

from core.constants import DARK_MARKET_SLOTS
from core.registry import DARK_MARKET_POOL, ITEMS_REGISTRY
from infrastructure.repositories import dark_market as repo


def week_key() -> str:
    """Ключ ISO-недели UTC: '2026-W29'. Ротация — понедельник 00:00 UTC."""
    return datetime.now(timezone.utc).strftime("%G-W%V")


def next_rotation_utc() -> str:
    """ISO-время ближайшего понедельника 00:00 UTC (для таймера на фронте)."""
    now = datetime.now(timezone.utc)
    days_ahead = (7 - now.weekday()) % 7 or 7
    nxt = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
    return nxt.isoformat()


def generate_market_slots() -> list[dict]:
    """DARK_MARKET_SLOTS уникальных товаров из пула, кол-во из qty_range,
    цена = base × qty (без скидок — рынок и так «нелегальный»)."""
    pool = DARK_MARKET_POOL.copy()
    random.shuffle(pool)
    slots = []
    for i, entry in enumerate(pool[:DARK_MARKET_SLOTS], start=1):
        qty = random.randint(*entry["qty_range"])
        slots.append({
            "slot": i, "item_id": entry["item_id"], "quantity": qty,
            "price_dark": float(entry["base_price_dark"] * qty),
        })
    return slots


async def ensure_market_fresh(db) -> list[dict]:
    """Вернуть товары недели, перегенерировав при смене ISO-недели."""
    key = week_key()
    if await repo.get_week_key(db) == key:
        return await repo.get_current(db)
    slots = generate_market_slots()
    await repo.save_slots(db, slots, key)
    return slots


def enrich(slots: list[dict]) -> list[dict]:
    """Добавить имя/описание из реестра для показа игроку."""
    out = []
    for s in slots:
        item = ITEMS_REGISTRY.get(s["item_id"], {})
        out.append({**s,
                    "item_name": item.get("name", s["item_id"]),
                    "item_description": item.get("description", "")})
    return out


async def purchase_slot(db, user_id: int, slot: int) -> tuple[bool, str]:
    """Купить слот недели (1 раз на игрока в неделю). Атомарно: списание 🌑
    + инвентарь + запись покупки в одной транзакции, с wallet_log."""
    key = week_key()
    deals = await repo.get_current(db)
    deal = next((d for d in deals if d["slot"] == slot), None)
    if not deal:
        return False, "Этот товар недоступен — рынок обновился."
    price = float(deal["price_dark"])
    item_id, qty = deal["item_id"], int(deal["quantity"])
    item_name = ITEMS_REGISTRY.get(item_id, {}).get("name", item_id)
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT COALESCE(user_balance_dark_mora,0), COALESCE(user_balance_mora,0), "
                "COALESCE(user_balance_diamonds,0) FROM users WHERE user_tg_id = ? FOR UPDATE",
                (user_id,),
            ) as c:
                row = await c.fetchone()
            if not row:
                return False, "Профиль не найден."
            dark_bal = float(row[0])
            if await repo.already_purchased(db, user_id, slot, key):
                return False, "Этот товар уже куплен на этой неделе."
            if dark_bal < price:
                return False, f"Нужно {price:.0f} 🌑 (у тебя {dark_bal:.0f})."
            dark_after = dark_bal - price
            await db.execute(
                "UPDATE users SET user_balance_dark_mora = ? WHERE user_tg_id = ?",
                (dark_after, user_id))
            await db.execute(
                "INSERT INTO wallet_log (user_id, delta_mora, delta_diamonds, delta_dark_mora, "
                "balance_mora_after, balance_diamonds_after, balance_dark_mora_after, source, note) "
                "VALUES (?, 0, 0, ?, ?, ?, ?, 'dark_market', ?)",
                (user_id, -price, float(row[1]), float(row[2]), dark_after, f"{item_id}×{qty}"))
            await db.execute(
                "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
                (user_id, item_id, qty, qty))
            await repo.record_purchase(db, user_id, slot, key)
        return True, f"🖤 Куплено: {qty}× {item_name} за {price:.0f} 🌑"
    except Exception as e:
        return False, f"Ошибка: {e}"
