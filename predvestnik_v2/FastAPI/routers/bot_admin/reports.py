"""Раздел «Жалобы»: очередь жалоб игроков из чатов («бот жалоба»).

Наказать нарушителя можно сразу из жалобы (варн, мут, бан в чате жалобы) или из его карточки в разделе
«Игроки и чаты»: действия и права те же. Жалобу берут в работу и закрывают: «нарушение подтверждено» или «отклонена».
Автору жалобы бот пишет в личку, чем закончилось (если личка с ботом открыта).
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from loguru import logger

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from FastAPI.routers.bot_admin import people
from FastAPI.routers.bot_admin.people import get_bot
from services import admin_people
from services import reports as reports_service

router = APIRouter(prefix="/bot-admin/api", tags=["bot-admin"])
_user = section("reports")
_ready = False


async def _tables(db=Depends(get_db)):
    """Таблицы жалоб создаются при старте бота; если старт не дошёл до них, создаём здесь (повторно безопасно)."""
    global _ready
    if not _ready:
        await reports_service.ensure_schema(db)
        _ready = True
ACTIONS = {"take": "in_work", "resolve": "resolved", "reject": "rejected"}
PUNISH = {"warn": "варн", "mute": "мут", "ban": "бан"}
NOTICE = {"resolved": "✅ Ваша жалоба №{id} рассмотрена: нарушение подтверждено. Спасибо!",
          "rejected": "📨 Ваша жалоба №{id} рассмотрена: нарушения не нашли."}


@router.get("/reports")
async def reports(kind: str = "open", user=Depends(_user), db=Depends(get_db), _=Depends(_tables)):
    conf = await reports_service.settings(db)
    show = user["rank"] >= conf["reporter_min_rank"]
    return {"items": await reports_service.listing(db, "closed" if kind == "closed" else "open", show_reporter=show),
            "counts": await reports_service.counts(db), "can_see_reporter": show,
            "punish": [{"key": k, "title": people.ACTIONS[k][0]} for k in PUNISH if user["rank"] >= people.ACTIONS[k][1]]}


async def _finish(db, user: dict, report: dict, status: str, note: str) -> None:
    """Сменить статус жалобы, записать в журнал и написать автору, чем закончилось."""
    rid = report["id"]
    if not await reports_service.set_status(db, rid, status, user["id"], note):
        raise HTTPException(409, "Жалоба уже закрыта.")
    await admin_people.audit(db, user["id"], f"report_{status}", user_id=report["target_id"], chat_id=report["chat_id"],
                             details={"report": rid, "reason": note} if note else {"report": rid})
    if status in NOTICE:
        try:
            await get_bot().send_message(report["reporter_id"], NOTICE[status].format(id=rid))
        except Exception as exc:   # игрок не открывал личку с ботом
            logger.debug(f"report {rid} notice failed: {exc}")


@router.post("/reports/{rid}")
async def report_action(rid: int, data: dict = Body(...), user=Depends(_user), db=Depends(get_db), _=Depends(_tables)):
    status = ACTIONS.get(str(data.get("action") or ""))
    if not status:
        raise HTTPException(400, "Неизвестное действие.")
    report = await reports_service.get(db, rid)
    if not report:
        raise HTTPException(404, "Жалоба не найдена.")
    await _finish(db, user, report, status, str(data.get("note") or "").strip()[:300])
    return {"ok": True, "message": reports_service.STATUS_TITLES[status] + "."}


@router.post("/reports/{rid}/punish")
async def report_punish(rid: int, data: dict = Body(...), user=Depends(_user), db=Depends(get_db), _=Depends(_tables)):
    """Наказать нарушителя прямо из жалобы (в чате, где подана жалоба) и, если не сказано иное, закрыть её."""
    action = str(data.get("action") or "")
    if action not in PUNISH:
        raise HTTPException(400, "Отсюда можно выдать варн, мут или бан.")
    report = await reports_service.get(db, rid)
    if not report:
        raise HTTPException(404, "Жалоба не найдена.")
    if report["status"] not in reports_service.OPEN:
        raise HTTPException(409, "Жалоба уже закрыта.")
    reason = str(data.get("reason") or "").strip()[:200] or f"жалоба №{rid}"
    result = await people.player_action(
        report["target_id"], {"action": action, "chat_id": report["chat_id"], "minutes": data.get("minutes"),
                              "reason": reason}, user, db)
    closed = bool(data.get("close", True))
    if closed:
        await _finish(db, user, report, "resolved", f"{PUNISH[action]}: {reason}"[:300])
    return {"ok": True, "message": result["message"] + (" Жалоба закрыта." if closed else "")}
