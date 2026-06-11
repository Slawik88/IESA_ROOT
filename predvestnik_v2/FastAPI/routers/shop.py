"""FastAPI/routers/shop.py — каталог и покупки.
purchase_item() из services.economy — та же функция что и у бота.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from FastAPI.deps import get_db, require_tg_user
from core.registry import ITEMS_REGISTRY
from infrastructure.repositories.economy import get_balance
from services.economy import EconomyService

router = APIRouter(prefix="/shop", tags=["shop"])

_BUYABLE_CATEGORIES = {"food", "egg", "utility", "booster", "donate"}


def _build_catalog(discount: float) -> list[dict]:
    result = []
    for item_id, item in ITEMS_REGISTRY.items():
        if item.get("category") not in _BUYABLE_CATEGORIES:
            continue
        price_mora = item.get("price_mora", 0)
        price_dia = item.get("price_diamonds", 0)
        price_zar = item.get("price_zarniki", 0)
        if not price_mora and not price_dia and not price_zar:
            continue  # крафт или гача — не продаётся

        result.append({
            "item_id":         item_id,
            "name":            item["name"],
            "category":        item.get("category", ""),
            "description":     item.get("description", ""),
            "price_mora":      int(price_mora * (1 - discount)) if price_mora else 0,
            "price_diamonds":  int(price_dia * (1 - discount)) if price_dia else 0,
            "price_zarniki":   price_zar,
            "discount_active": discount > 0,
        })
    return result


@router.get("/")
async def get_shop(db=Depends(get_db), user=Depends(require_tg_user)):
    """Каталог магазина с ценами (учитывает скидку черепахи)."""
    eco = EconomyService(db)
    discount = await eco.get_turtle_discount(user["id"])
    bal = await get_balance(db, user["id"])
    return {
        "mora":     float(bal["user_balance_mora"] or 0),
        "diamonds": float(bal["user_balance_diamonds"] or 0),
        "items":    _build_catalog(discount),
    }


class BuyRequest(BaseModel):
    item_id:  str
    quantity: int = Field(default=1, ge=1, le=99)


@router.post("/buy")
async def buy_item(
    body: BuyRequest,
    db=Depends(get_db),
    user=Depends(require_tg_user),
):
    """Купить предмет. Использует EconomyService.purchase_item() — та же логика что в боте."""
    eco = EconomyService(db)
    ok, message = await eco.purchase_item(user["id"], body.item_id, body.quantity)

    if not ok:
        raise HTTPException(status_code=400, detail=message)

    await db.commit()

    item = ITEMS_REGISTRY.get(body.item_id, {})
    return {
        "ok":       True,
        "message":  message,
        "item_name": item.get("name", body.item_id),
        "quantity": body.quantity,
    }
