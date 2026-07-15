"""FastAPI/routers/barracks.py — Боёвка 3.0: Казарма (юниты, призыв, отряд).
Тонкий адаптер над services/barracks.py."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from services import barracks

router = APIRouter(prefix="/barracks", tags=["barracks"])


class UnitRequest(BaseModel):
    unit_id: str


class SquadRequest(BaseModel):
    slots: dict[str, str | None]


@router.get("")
async def overview(db=Depends(get_db), user=Depends(require_tg_user)):
    return await barracks.get_barracks(db, user["id"])


@router.post("/starter")
async def starter(body: UnitRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await barracks.pick_starter(db, user["id"], body.unit_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


@router.post("/summon")
async def summon(db=Depends(get_db), user=Depends(require_tg_user)):
    ok, res = await barracks.summon(db, user["id"])
    if not ok:
        raise HTTPException(400, str(res))
    return {"ok": True, **res}


@router.post("/levelup")
async def levelup(body: UnitRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await barracks.level_up(db, user["id"], body.unit_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


@router.post("/engrave")
async def engrave(body: UnitRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await barracks.engrave(db, user["id"], body.unit_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


@router.post("/unlock")
async def unlock(body: UnitRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await barracks.unlock_by_shards(db, user["id"], body.unit_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


@router.post("/squad")
async def set_squad(body: SquadRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await barracks.set_squad(db, user["id"], body.slots)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}
