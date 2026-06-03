"""FastAPI/routers/daily_deal.py — акция дня с таймером обновления."""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.economy import get_balance
from services.daily_deal import ensure_deals_fresh
from core.registry import ITEMS_REGISTRY

router = APIRouter(prefix="/daily-deal", tags=["daily-deal"])


def _next_midnight_utc() -> str:
    """ISO timestamp of next UTC midnight (when deals refresh)."""
    now = datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.isoformat()


@router.get("/")
async def get_deals(db=Depends(get_db), user=Depends(require_tg_user)):
    """Актуальные предметы акции дня + время до обновления."""
    raw_deals = await ensure_deals_fresh(db)
    bal = await get_balance(db, user["id"])

    # Enrich each deal with display name and description from ITEMS_REGISTRY
    deals = []
    for deal in raw_deals:
        item = ITEMS_REGISTRY.get(deal.get("item_id", ""), {})
        deals.append({
            **deal,
            "item_name": item.get("name", deal.get("item_id", "?")),
            "item_description": item.get("description", ""),
        })

    return {
        "deals": deals,
        "refreshes_at": _next_midnight_utc(),
        "mora": float(bal["user_balance_mora"] or 0),
        "diamonds": float(bal["user_balance_diamonds"] or 0),
    }


class BuyDealRequest(BaseModel):
    deal_id: int


@router.post("/buy")
async def buy_deal(body: BuyDealRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Купить предмет из акции дня."""
    from infrastructure.repositories.daily_deal import get_deal, mark_purchased, get_user_purchase_count
    from infrastructure.repositories.economy import add_balance, add_item

    deal = await get_deal(db, body.deal_id)
    if not deal or deal.get("expires_at") < datetime.now(timezone.utc).isoformat()[:19]:
        raise HTTPException(400, "Этот лот акции недоступен.")

    already = await get_user_purchase_count(db, user["id"], body.deal_id)
    if already >= deal.get("max_per_user", 1):
        raise HTTPException(400, "Вы уже купили этот лот сегодня.")

    bal = await get_balance(db, user["id"])
    if deal.get("price_mora", 0) > 0:
        if bal["user_balance_mora"] < deal["price_mora"]:
            raise HTTPException(400, f"Нужно {deal['price_mora']:.0f} 🪙.")
        await add_balance(db, user["id"], mora=-deal["price_mora"], commit=False,
                          source="daily_deal", note=deal.get("item_id",""))
    elif deal.get("price_diamonds", 0) > 0:
        if bal["user_balance_diamonds"] < deal["price_diamonds"]:
            raise HTTPException(400, f"Нужно {deal['price_diamonds']} 💎.")
        await add_balance(db, user["id"], diamonds=-deal["price_diamonds"], commit=False,
                          source="daily_deal", note=deal.get("item_id",""))
    else:
        raise HTTPException(400, "Нет цены у этого предмета.")

    await add_item(db, user["id"], deal["item_id"], deal.get("quantity", 1))
    await mark_purchased(db, user["id"], body.deal_id)
    await db.commit()
    return {"ok": True, "item_id": deal["item_id"], "qty": deal.get("quantity", 1)}
