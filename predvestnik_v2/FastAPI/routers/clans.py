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


class BoardCreateRequest(BaseModel):
    item_id: str
    qty: int


class BoardFillRequest(BaseModel):
    request_id: int
    qty: int


class BoardCancelRequest(BaseModel):
    request_id: int


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


# ── Доска Запросов (БЛОК19 Ч.5) ─────────────────────────────────────────────────


@router.post("/request/create")
async def clans_request_create(body: BoardCreateRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await svc.request_create(db, user["id"], body.item_id, body.qty)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


@router.post("/request/fill")
async def clans_request_fill(body: BoardFillRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await svc.request_fill(db, user["id"], body.request_id, body.qty)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


@router.post("/request/cancel")
async def clans_request_cancel(body: BoardCancelRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await svc.request_cancel(db, user["id"], body.request_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}
