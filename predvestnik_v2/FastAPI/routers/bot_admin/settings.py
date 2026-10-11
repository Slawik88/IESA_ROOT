"""Раздел «Настройки бота»: переводы между игроками и жалобы (куда идёт отчёт, кто видит автора)."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from bot.chat import ranks
from bot.chat import settings as bot_settings
from bot.chat.global_ranks import BOT_RANKS, CREATOR, bot_rank_name
from bot.chat.settings import CURRENCY_VIEW, NEVER_TRANSFERABLE
from services import admin_people
from services import reports as reports_service

router = APIRouter(prefix="/bot-admin/api", tags=["bot-admin"])
_user = section("settings")
# Переводимыми могут быть только текущие валюты ленты (тёмная мора — легаси).
CANDIDATES = ("mora", "diamonds", "essence", "zarniki")


@router.get("/settings")
async def get_settings(user=Depends(_user), db=Depends(get_db)):
    allowed = set(await bot_settings.transferable(db))
    return {"transfer": [
        {"code": c, "title": f"{CURRENCY_VIEW[c].icon} {CURRENCY_VIEW[c].label}", "enabled": c in allowed,
         "locked": c in NEVER_TRANSFERABLE} for c in CANDIDATES],
        "reports": await reports_service.settings(db),
        "report_options": {
            "chat_ranks": [{"value": i, "title": ranks.rank_name(i)} for i in range(1, ranks.OWNER + 1)],
            "staff_ranks": [{"value": i, "title": bot_rank_name(i)} for i in range(1, CREATOR + 1)]}}


@router.post("/settings/transfer")
async def set_transfer(data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    codes = [str(c) for c in data.get("currencies") or []]
    if any(c not in CANDIDATES for c in codes):
        raise HTTPException(400, "Неизвестная валюта.")
    if any(c in NEVER_TRANSFERABLE for c in codes):
        raise HTTPException(400, "Зарники и эссенцию переводить нельзя никогда.")
    await bot_settings.set_json(db, bot_settings.TRANSFERABLE_KEY, codes, user["id"])
    await admin_people.audit(db, user["id"], "transfer", details={"currencies": codes})
    return await get_settings(user=user, db=db)


@router.post("/settings/reports")
async def set_reports(data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    try:
        saved = await reports_service.save_settings(db, data, user["id"])
    except reports_service.ReportError as exc:
        raise HTTPException(400, str(exc))
    await admin_people.audit(db, user["id"], "report_settings", details=saved)
    return await get_settings(user=user, db=db)
