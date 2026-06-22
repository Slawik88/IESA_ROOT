"""FastAPI/routers/cosmetics.py — Конструктор внешнего вида профиля.

Каталог косметики, покупка (мульти/альт-валюта), экипировка слотов. Только
косметика, без игрового преимущества. Логика — в services/cosmetics.py.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from services.cosmetics import buy, equip, get_catalog, set_welcome, unequip

router = APIRouter(prefix="/cosmetics", tags=["cosmetics"])


@router.get("/")
async def cosmetics_catalog(db=Depends(get_db), user=Depends(require_tg_user)):
    return await get_catalog(db, user["id"])


class BuyRequest(BaseModel):
    cosmetic_id: str
    option_index: int = 0


@router.post("/buy")
async def cosmetics_buy(body: BuyRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await buy(db, user["id"], body.cosmetic_id, body.option_index)
    if not ok:
        raise HTTPException(400, msg)
    await db.commit()
    return {"ok": True, "message": msg}


class EquipRequest(BaseModel):
    cosmetic_id: str


@router.post("/equip")
async def cosmetics_equip(body: EquipRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await equip(db, user["id"], body.cosmetic_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


class UnequipRequest(BaseModel):
    slot: str


@router.post("/unequip")
async def cosmetics_unequip(body: UnequipRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await unequip(db, user["id"], body.slot)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


class WelcomeRequest(BaseModel):
    animation_id: str


@router.post("/welcome")
async def cosmetics_welcome(body: WelcomeRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await set_welcome(db, user["id"], body.animation_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}
