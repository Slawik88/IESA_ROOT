"""Private wardrobe endpoints for the release Mini App.

No catalogue checkout, gifting, preset or direct-Stars route is registered
here.  Ownership is durable; public visibility is determined separately by
the active-VIP projection in ``services.cosmetics``.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tg_user
from services.cosmetics import equip, get_fitting_inventory, unequip


router = APIRouter(prefix="/appearance", tags=["appearance"])


class EquipRequest(BaseModel):
    cosmetic_id: str = Field(min_length=1, max_length=160)


class UnequipRequest(BaseModel):
    slot: str = Field(min_length=1, max_length=40)


@router.get("/me")
async def my_wardrobe(db=Depends(get_db), user=Depends(require_tg_user)):
    return await get_fitting_inventory(db, int(user["id"]))


@router.post("/equip")
async def equip_my_cosmetic(body: EquipRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, message = await equip(db, int(user["id"]), body.cosmetic_id)
    if not ok:
        raise HTTPException(status_code=409, detail=message)
    return {"ok": True, "message": message}


@router.post("/unequip")
async def unequip_my_cosmetic(body: UnequipRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, message = await unequip(db, int(user["id"]), body.slot)
    if not ok:
        raise HTTPException(status_code=409, detail=message)
    return {"ok": True, "message": message}
