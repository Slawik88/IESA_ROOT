"""Раздел «Журнал»: общая лента действий персонала с фильтрами по человеку, виду и сроку."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from FastAPI.routers.bot_admin.safe import AdminRoute
from services import admin_people

router = APIRouter(prefix="/bot-admin/api", tags=["bot-admin"], route_class=AdminRoute)
_user = section("journal")


@router.get("/journal")
async def journal(kind: str = "", actor: int = 0, days: int = 7, before: str = "", user_id: int = 0, chat_id: int = 0,
                  user=Depends(_user), db=Depends(get_db)):
    scope = {"kind": kind, "actor_id": actor or None, "user_id": user_id or None, "chat_id": chat_id or None, "days": days}
    try:
        return await admin_people.feed(db, before=before, **scope)
    except ValueError:   # битая дата в курсоре — начинаем с начала
        return await admin_people.feed(db, **scope)


@router.get("/journal/export")
async def journal_export(kind: str = "", actor: int = 0, days: int = 7, user_id: int = 0, chat_id: int = 0,
                         user=Depends(_user), db=Depends(get_db)):
    """Тот же журнал файлом CSV: период до 90 дней, до 5000 строк. Выгрузка сама пишется в журнал."""
    text, count = await admin_people.export_csv(db, kind=kind, actor_id=actor or None, user_id=user_id or None,
                                                chat_id=chat_id or None, days=days)
    await admin_people.audit(db, user["id"], "journal_export", user_id=user_id or None, chat_id=chat_id or None,
                             details={"days": max(1, min(days, admin_people.FEED_DAYS_MAX)), "rows": count, "kind": kind})
    return Response(text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="journal-{days}d.csv"'})
