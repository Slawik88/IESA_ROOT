"""Раздел «Жалобы»: очередь жалоб игроков из чатов («бот жалоба»).

Наказать нарушителя — из его карточки в разделе «Игроки и чаты» (те же действия и права);
здесь жалобу берут в работу и закрывают: «нарушение подтверждено» или «отклонена».
Автору жалобы бот пишет в личку, чем закончилось (если личка с ботом открыта).
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from loguru import logger

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from FastAPI.routers.bot_admin.people import get_bot
from services import admin_people
from services import reports as reports_service

router = APIRouter(prefix="/bot-admin/api", tags=["bot-admin"])
_user = section("reports")
ACTIONS = {"take": "in_work", "resolve": "resolved", "reject": "rejected"}
NOTICE = {"resolved": "✅ Ваша жалоба №{id} рассмотрена: нарушение подтверждено. Спасибо!",
          "rejected": "📨 Ваша жалоба №{id} рассмотрена: нарушения не нашли."}


@router.get("/reports")
async def reports(kind: str = "open", user=Depends(_user), db=Depends(get_db)):
    return {"items": await reports_service.listing(db, "closed" if kind == "closed" else "open"),
            "counts": await reports_service.counts(db)}


@router.post("/reports/{rid}")
async def report_action(rid: int, data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    status = ACTIONS.get(str(data.get("action") or ""))
    if not status:
        raise HTTPException(400, "Неизвестное действие.")
    report = await reports_service.get(db, rid)
    if not report:
        raise HTTPException(404, "Жалоба не найдена.")
    note = str(data.get("note") or "").strip()[:300]
    if not await reports_service.set_status(db, rid, status, user["id"], note):
        raise HTTPException(409, "Жалоба уже закрыта.")
    await admin_people.audit(db, user["id"], f"report_{status}", user_id=report["target_id"], chat_id=report["chat_id"],
                             details={"report": rid, "reason": note} if note else {"report": rid})
    if status in NOTICE:
        try:
            await get_bot().send_message(report["reporter_id"], NOTICE[status].format(id=rid))
        except Exception as exc:   # игрок не открывал личку с ботом
            logger.debug(f"report {rid} notice failed: {exc}")
    return {"ok": True, "message": reports_service.STATUS_TITLES[status] + "."}
