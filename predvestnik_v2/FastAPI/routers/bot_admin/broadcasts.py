"""Раздел «Рассылка»: сообщение от бота во все чаты или всем игрокам в личку."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, Body, Depends, HTTPException

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from FastAPI.routers.bot_admin.people import get_bot
from infrastructure.database import get_pool
from infrastructure.pg_adapter import PGAdapter
from services import admin_people
from services import broadcasts as broadcasts_service

router = APIRouter(prefix="/bot-admin/api", tags=["bot-admin"])
_user = section("broadcast")


@asynccontextmanager
async def _pool_db():
    async with get_pool().acquire() as conn:
        yield PGAdapter(conn)


@router.get("/broadcasts")
async def broadcasts(user=Depends(_user), db=Depends(get_db)):
    return {"items": await broadcasts_service.listing(db),
            "audiences": [{"key": k, "title": t} for k, t in broadcasts_service.AUDIENCES.items()],
            "sizes": await broadcasts_service.audience_sizes(db)}


@router.post("/broadcasts")
async def broadcast_create(data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    audience = str(data.get("audience") or "")
    text = str(data.get("text") or "").strip()
    try:
        bid, new, targets = await broadcasts_service.create(db, user["id"], audience, text,
                                                            str(data.get("request_id") or "")[:64])
    except broadcasts_service.BroadcastError as exc:
        raise HTTPException(400, str(exc))
    if new:
        await admin_people.audit(db, user["id"], "broadcast",
                                 details={"audience": broadcasts_service.AUDIENCES[audience], "text": text[:500],
                                          "total": len(targets), "broadcast": bid})
        broadcasts_service.start(get_bot(), _pool_db, bid, audience, text, targets)
    return {"ok": True, "id": bid, "message": f"Рассылка запущена: {len(targets)} получателей." if new else "Уже запущена."}


@router.post("/broadcasts/{bid}/stop")
async def broadcast_stop(bid: int, user=Depends(_user), db=Depends(get_db)):
    if not await broadcasts_service.stop(db, bid):
        raise HTTPException(409, "Рассылка уже закончилась.")
    await admin_people.audit(db, user["id"], "broadcast_stop", details={"broadcast": bid})
    return {"ok": True, "message": "Рассылка остановлена."}
