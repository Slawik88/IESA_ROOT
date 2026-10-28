"""Authenticated web adapter for the same chat purge used by Telegram commands.

Compatibility (S05): the screen shipped before S05 calls these endpoints without new parameters and gets the old
answers. The new screen asks for ``live=1`` (WebSocket pushes instead of a 2 s poll, ETag) and ``background=1``
(202 at once; the list is prepared in the background and shown in ``preparing`` of the chat view).
"""
from datetime import date, timedelta
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from FastAPI import purge_live
from FastAPI.deps import get_db, require_tg_user
from FastAPI.routers.bot_admin.people import get_bot
from bot.chat import purge as bridge
from bot.chat.framework import UsageError
from bot.chat.tracking import local_now
from services import purge as flow

router = APIRouter(prefix="/purge-v1", tags=["purge-v1"])


class StartBody(BaseModel):
    action_id: str = Field(min_length=1, max_length=96)
    norm: int = Field(ge=1, le=100000)
    date_from: date
    date_to: date


class DecisionBody(BaseModel):
    session_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    action: str = Field(pattern="^(forgive|warn|mute|kick|ban)$")
    action_id: str = Field(min_length=1, max_length=96)


class FinishBody(BaseModel):
    session_id: int = Field(gt=0)


class ReconcileBody(FinishBody):
    user_id: int = Field(gt=0)
    applied: bool
    reason: str = Field(min_length=12, max_length=300)


async def _authorize(db, user, cid: int, *, reading: bool = False, fresh: bool = False):
    try:
        await bridge.authorize_shared(get_bot(), db, cid, int(user["id"]), action="read" if reading else None, fresh=fresh)
    except flow.PurgeUnavailable as error:
        raise HTTPException(503, str(error))
    except flow.PurgeConflict as error:
        purge_live.unwatch(cid, int(user["id"]))
        raise HTTPException(403, str(error))


@router.get("/chats")
async def chats(offset: int = Query(0, ge=0, le=1_000_000), db=Depends(get_db), user=Depends(require_tg_user)):
    from infrastructure.repositories import moderation_chats
    from bot.chat.access import is_developer
    return await moderation_chats.listing(db, user_id=int(user["id"]), offset=offset,
                                           purge_only=True, developer=is_developer(int(user["id"])))


@router.get("/access")
async def access(db=Depends(get_db), user=Depends(require_tg_user)):
    """Only "is there a chat to purge" for the entry in «Ещё»: no counting of chats and their members (S04)."""
    from infrastructure.repositories import moderation_chats
    from bot.chat.access import is_developer
    return {"available": await moderation_chats.has_purge_access(db, user_id=int(user["id"]),
                                                                 developer=is_developer(int(user["id"])))}


@router.get("/chats/{cid}")
async def current(request: Request, cid: int, page: int = Query(0, ge=0, le=10000),
                  mode: str = Query("pending", pattern="^(pending|decided|all)$"), live: bool = Query(False),
                  db=Depends(get_db), user=Depends(require_tg_user)):
    await _authorize(db, user, cid, reading=True)
    result = await flow.view(db, chat_id=cid, page=page, mode=mode)
    if not result["active"]:
        today = local_now().date()
        result["defaults"] = {"date_from": (today-timedelta(days=7)).isoformat(),
                              "date_to": (today-timedelta(days=1)).isoformat(), "today": today.isoformat()}
    if not live:
        return result
    purge_live.watch(cid, int(user["id"]))
    job = bridge.start_job(cid)
    result["preparing"] = job.view() if job and not result["active"] and job.state != "started" else None
    result["dossiers_running"] = bool(result["active"]) and bridge.dossier_queue_running(int(result["session"]["id"]))
    body = json.dumps(jsonable_encoder(result), ensure_ascii=False, separators=(",", ":")).encode()
    etag = f'"{hashlib.sha256(body).hexdigest()[:32]}"'
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(body, media_type="application/json", headers=headers)


@router.post("/chats/{cid}/start")
async def start(cid: int, body: StartBody, background: bool = Query(False), db=Depends(get_db), user=Depends(require_tg_user)):
    await _authorize(db, user, cid)
    if body.date_to < body.date_from:
        raise HTTPException(400, "Конец периода раньше начала.")
    args = f"{body.norm} {bridge.fmt(body.date_from)}-{bridge.fmt(body.date_to)}"
    try:
        plan = bridge.plan_purge(args, local_now().date(), None)
        if isinstance(plan, str):
            raise flow.PurgeConflict(plan)
        receipt = await flow.existing_start(db, chat_id=cid, actor=int(user["id"]), action_id=body.action_id,
                                            norm=plan.norm, date_from=plan.start.isoformat(), date_to=plan.end.isoformat())
        if receipt is None and background:
            job = bridge.launch_start(get_bot(), cid, int(user["id"]), plan, body.action_id)
            return JSONResponse({"ok": True, "accepted": True, "job": job.view(),
                                 "message": "Готовлю список тех, кто не набрал норму."}, status_code=202)
        if receipt is None:
            receipt = await bridge.prepare_and_start(get_bot(), db, cid, int(user["id"]), plan, body.action_id)
        sid, active = receipt["session_id"], receipt["active"]
    except flow.PurgeUnavailable as error:
        raise HTTPException(503, str(error))
    except (flow.PurgeConflict, UsageError) as error:
        raise HTTPException(409, str(error))
    return {"ok": True, "session_id": sid, "active": active, "message": "Чистка началась. Решения можно принимать здесь или в Telegram." if active else "Этот запуск уже обработан, чистка завершена."}


@router.post("/chats/{cid}/decision")
async def decision(cid: int, body: DecisionBody, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await bridge.decide_shared(get_bot(), db, cid, body.session_id, body.user_id,
                                         int(user["id"]), body.action, body.action_id)
    except flow.PurgeUnavailable as error:
        raise HTTPException(503, str(error))
    except flow.PurgeConflict as error:
        raise HTTPException(409, str(error))


@router.post("/chats/{cid}/finish")
async def finish(cid: int, body: FinishBody, db=Depends(get_db), user=Depends(require_tg_user)):
    await _authorize(db, user, cid, reading=True, fresh=True)
    try:
        result = await flow.complete(db, chat_id=cid, actor=int(user["id"]), expected_session=body.session_id)
    except flow.PurgeConflict as error:
        raise HTTPException(409, str(error))
    purge_live.changed(cid)
    return {"ok": True, **result}


@router.post("/chats/{cid}/reconcile")
async def reconcile(cid: int, body: ReconcileBody, db=Depends(get_db), user=Depends(require_tg_user)):
    async def authorize(actual, target, action):
        if actual != cid:
            raise flow.PurgeConflict("Чистка относится к другому чату.")
        await bridge.authorize_shared(get_bot(), db, cid, int(user["id"]), action="read", fresh=True)
    async def materialize(row, applied):
        await bridge.materialize_reconciled(get_bot(), db, cid, row, applied=applied)
    try:
        return await flow.reconcile(db, session_id=body.session_id, user_id=body.user_id, actor=int(user["id"]),
                                    applied=body.applied, reason=body.reason, authorize=authorize, materialize=materialize)
    except flow.PurgeUnavailable as error:
        raise HTTPException(503, str(error))
    except flow.PurgeConflict as error:
        raise HTTPException(409, str(error))
    finally:
        purge_live.changed(cid)
