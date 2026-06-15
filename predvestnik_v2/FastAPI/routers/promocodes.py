"""FastAPI/routers/promocodes.py — активация промокодов."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from core.registry import ITEMS_REGISTRY
from services.promocodes import activate_promocode, PromoError

router = APIRouter(prefix="/promo", tags=["promo"])


class RedeemRequest(BaseModel):
    code: str


@router.post("/redeem")
async def redeem(body: RedeemRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Активировать промокод."""
    code = body.code.strip().upper()
    if not code:
        raise HTTPException(400, "Введите промокод.")
    try:
        result = await activate_promocode(db, user["id"], code)
        await db.commit()
        # Resolve item_id -> name for the frontend, same convention as
        # /vip/status, /battle_pass/status, /themes/ (_resolve_items).
        result["items"] = [
            {"item_id": item_id, "name": ITEMS_REGISTRY.get(item_id, {}).get("name", item_id), "qty": qty}
            for item_id, qty in result.get("items", {}).items()
        ]
        return {"ok": True, "message": "✅ Промокод активирован!", "reward": result}
    except PromoError as e:
        raise HTTPException(400, str(e))
