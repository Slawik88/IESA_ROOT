"""Раздел «Журнал»: общая лента действий персонала с фильтрами по человеку, виду и сроку."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from FastAPI.routers.bot_admin.safe import AdminRoute
from services import admin_people, admin_security

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
async def journal_export(kind: str = "", actor: int = 0, days: int = 7, user_id: int = 0, chat_id: int = 0, deliver: str = "",
                         user=Depends(_user), db=Depends(get_db)):
    """Тот же журнал файлом CSV: период до 90 дней, до 5000 строк. Выгрузка сама пишется в журнал.
    deliver=dm — файл приходит сотруднику в личку от бота: внутри Telegram на телефоне скачать файл со страницы нельзя."""
    admin_security.rate_limit(user, "journal_export")
    days = max(1, min(int(days or 7), admin_people.FEED_DAYS_MAX))
    text, count = await admin_people.export_csv(db, kind=kind, actor_id=actor or None, user_id=user_id or None,
                                                chat_id=chat_id or None, days=days)
    await admin_people.audit(db, user["id"], "journal_export", user_id=user_id or None, chat_id=chat_id or None,
                             details={"days": days, "rows": count, "kind": kind})
    if deliver == "dm":
        from aiogram.types import BufferedInputFile
        from FastAPI.routers.bot_admin.people import get_bot
        try:
            await get_bot().send_document(user["id"], BufferedInputFile(text.encode("utf-8"), filename=f"journal-{days}d.csv"),
                                          caption=f"Журнал админки: строк {count}.")
        except Exception as exc:
            raise HTTPException(409, "Не удалось отправить в личку: напишите боту в личку /start и повторите.") from exc
        return {"ok": True, "message": f"Таблица ({count} строк) отправлена вам в личку от бота."}
    return Response(text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="journal-{days}d.csv"'})
