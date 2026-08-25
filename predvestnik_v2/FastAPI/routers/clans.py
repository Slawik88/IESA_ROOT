"""FastAPI/routers/clans.py — веб-адаптер кланов (тонкий слой над services.clans)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from services import clans as svc

router = APIRouter(prefix="/clans", tags=["clans"])


class CreateClanRequest(BaseModel):
    name: str
    tag: str
    description: str = ""
    emblem: str = "🛡"


class JoinClanRequest(BaseModel):
    clan_id: int


@router.get("/")
async def clans_overview(db=Depends(get_db), user=Depends(require_tg_user)):
    return await svc.get_overview(db, user["id"])


@router.post("/create")
async def clans_create(body: CreateClanRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg, cid = await svc.create(db, user["id"], body.name, body.tag, body.description, body.emblem)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg, "clan_id": cid}


@router.post("/join")
async def clans_join(body: JoinClanRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await svc.join(db, user["id"], body.clan_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


@router.post("/leave")
async def clans_leave(db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await svc.leave(db, user["id"])
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


# R3: Доска Запросов удалена — кооперация переехала в Бездну клана (/clans2/abyss).


# ── Клан-лавка (сток clan_coins) ─────────────────────────────────────────────


class ShopBuyRequest(BaseModel):
    shop_id: str


@router.post("/shop/buy")
async def clans_shop_buy(body: ShopBuyRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    raise HTTPException(410, "Старая клановая лавка закрыта. Накопленная история клана сохранена как Основание.")
