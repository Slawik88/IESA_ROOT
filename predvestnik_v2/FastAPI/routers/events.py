"""FastAPI/routers/events.py — активные игровые события."""
from fastapi import APIRouter, Depends

from FastAPI.deps import get_db, require_tg_user
from core.constants import EXCHANGE_RATE_MORA_PER_DIAMOND, EXCHANGE_DAILY_CAP_DIAMONDS
from core.registry import ITEMS_REGISTRY, GACHA_RATES
from infrastructure.repositories.exchange import get_active_event, get_scheduled_event

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/")
async def active_events(db=Depends(get_db), user=Depends(require_tg_user)):
    """Все активные и ближайшие события."""
    exchange_active = await get_active_event(db)
    exchange_next = await get_scheduled_event(db) if not exchange_active else None

    # Daily deal items
    deals = []
    try:
        async with db.execute(
            "SELECT item_id, quantity, price_mora, price_diamonds FROM daily_deal_current LIMIT 5"
        ) as c:
            deal_rows = await c.fetchall()
        for r in (deal_rows or []):
            item = ITEMS_REGISTRY.get(r[0], {})
            base_price = item.get("price_mora", 0) or 0
            deals.append({
                "item_id": r[0],
                "name": item.get("name", r[0]),
                "price": float(r[2] or 0),
                "price_dia": float(r[3] or 0),
                "original": float(base_price),
                "qty": r[1],
            })
    except Exception:
        pass

    # Gacha spin types with rates overview
    gacha = [
        {
            "spin_type": stype,
            "label": stype.capitalize(),
            "rates": {rarity: pct for rarity, pct in rates.items() if pct > 0},
        }
        for stype, rates in GACHA_RATES.items()
    ]

    return {
        "exchange_active": dict(exchange_active) if exchange_active else None,
        "exchange_next": dict(exchange_next) if exchange_next else None,
        "exchange_rate": EXCHANGE_RATE_MORA_PER_DIAMOND,
        "exchange_cap": EXCHANGE_DAILY_CAP_DIAMONDS,
        "daily_deals": deals,
        "gacha_types": gacha,
    }
