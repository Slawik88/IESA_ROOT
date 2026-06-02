"""FastAPI/routers/gacha.py — крутки гачи."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from core.constants import SPIN_COSTS, SPIN_TYPE_LABELS, SPIN_TOKEN_IDS
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.economy import get_balance, get_item_quantity
from services.gacha import roll_single

router = APIRouter(prefix="/gacha", tags=["gacha"])


@router.get("/")
async def gacha_info(db=Depends(get_db), user=Depends(require_tg_user)):
    """Типы круток, стоимость и наличие жетонов у пользователя."""
    bal = await get_balance(db, user["id"])
    types = []
    for spin_type, cost in SPIN_COSTS.items():
        token_qty = await get_item_quantity(db, user["id"], SPIN_TOKEN_IDS.get(spin_type, ""))
        types.append({
            "spin_type":  spin_type,
            "label":      SPIN_TYPE_LABELS.get(spin_type, spin_type),
            "cost_mora":  cost["mora"],
            "cost_dia":   cost["diamonds"],
            "token_qty":  token_qty,
        })
    return {"mora": float(bal["user_balance_mora"] or 0), "spin_types": types}


class SpinRequest(BaseModel):
    spin_type: str


@router.post("/spin")
async def spin(body: SpinRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Один спин выбранного типа крутки."""
    ok, result = await roll_single(db, user["id"], body.spin_type)
    if not ok:
        raise HTTPException(400, result)
    await db.commit()
    return result
