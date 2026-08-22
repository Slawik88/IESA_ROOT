"""FastAPI/routers/shop.py — каталог и покупки.
purchase_item() из services.economy — та же функция что и у бота.
"""
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from FastAPI.deps import get_db, require_tg_user, require_module
from core.registry import ITEMS_REGISTRY
from infrastructure.repositories.economy import get_balance
from services.economy import EconomyService
from services.achievements import increment_metric as ach_incr

router = APIRouter(prefix="/shop", tags=["shop"], dependencies=[Depends(require_module("module_shop"))])

_BUYABLE_CATEGORIES = {"food", "utility", "booster", "donate"}

# Per-category bulk-buy caps — same limits as bot/handlers/shop.py::QTY_MAX_CAP,
# so the website can't bulk-buy past what the bot allows in one click.
_QTY_MAX_CAP = {"food": 99, "utility": 5}


def _build_catalog(eco: EconomyService, discount: float) -> list[dict]:
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
            # apply_discount_fraction() is the same helper purchase_item() uses, so the
            # displayed price always matches what actually gets charged.
            "price_mora":      eco.apply_discount_fraction(price_mora, discount) if price_mora else 0,
            "price_diamonds":  eco.apply_discount_fraction(price_dia, discount) if price_dia else 0,
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
        "zarniki":  float(bal["user_balance_zarniki"] or 0),
        "items":    _build_catalog(eco, discount),
    }


class BuyRequest(BaseModel):
    item_id:  str
    quantity: int = Field(default=1, ge=1, le=99)


@router.post("/buy")
async def buy_item(
    body: BuyRequest,
    db=Depends(get_db),
    user=Depends(require_tg_user),
    request_key: str = Header(alias="Idempotency-Key"),
):
    """Купить предмет. Использует EconomyService.purchase_item() — та же логика что в боте."""
    item = ITEMS_REGISTRY.get(body.item_id, {})
    cap = _QTY_MAX_CAP.get(item.get("category", ""), 99)
    if body.quantity > cap:
        raise HTTPException(status_code=400, detail=f"Максимум: {cap} шт.")
    if not request_key.strip() or len(request_key.strip()) > 120:
        raise HTTPException(status_code=400, detail="Idempotency-Key должен содержать 1–120 символов.")

    eco = EconomyService(db)
    ok, message = await eco.purchase_item(
        user["id"], body.item_id, body.quantity,
        idempotency_key=f"shop:{request_key.strip()}",
    )

    if not ok:
        raise HTTPException(status_code=400, detail=message)

    # Track patron achievement (mora spent in shop) — same as bot's cb_shop_do_buy.
    prices = await eco.get_item_prices(body.item_id, user["id"])
    mora_spent = prices["mora"] * body.quantity
    # An exact HTTP retry returns the original purchase and must not advance
    # secondary counters a second time.
    if mora_spent > 0 and message == "Покупка завершена.":
        try:
            await ach_incr(db, user["id"], "total_mora_spent_shop", delta=mora_spent)
        except Exception:
            pass

    await db.commit()

    return {
        "ok":       True,
        "message":  message,
        "item_name": item.get("name", body.item_id),
        "quantity": body.quantity,
    }
