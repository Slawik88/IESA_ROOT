"""Раздел «Журнал»: общая лента действий персонала с фильтрами по человеку, виду и сроку."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from services import admin_people

router = APIRouter(prefix="/bot-admin/api", tags=["bot-admin"])
_user = section("journal")


@router.get("/journal")
async def journal(kind: str = "", actor: int = 0, days: int = 7, before: str = "", user=Depends(_user), db=Depends(get_db)):
    try:
        return await admin_people.feed(db, kind=kind, actor_id=actor or None, days=days, before=before)
    except ValueError:   # битая дата в курсоре — начинаем с начала
        return await admin_people.feed(db, kind=kind, actor_id=actor or None, days=days)
