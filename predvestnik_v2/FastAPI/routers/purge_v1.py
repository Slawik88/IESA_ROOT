"""Authenticated web adapter for the same chat purge used by Telegram commands."""
from datetime import date
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tg_user
from FastAPI.routers.bot_admin.people import get_bot
from bot.chat import purge as bridge, ranks
from bot.chat.admin_chat import admin_chat_of
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


async def _authorize(db, user, cid: int, *, reading: bool = False):
    try:
        await bridge.authorize_shared(get_bot(), db, cid, int(user["id"]), action="read" if reading else None)
    except flow.PurgeConflict as error:
        raise HTTPException(403, str(error))


@router.get("/chats")
async def chats(db=Depends(get_db), user=Depends(require_tg_user)):
    async with db.execute("SELECT s.chat_tg_id,c.chat_title FROM user_chat_stats s JOIN chat_settings c ON c.chat_id=s.chat_tg_id "
                          "WHERE s.user_tg_id=? AND s.is_left=FALSE ORDER BY c.chat_title LIMIT 100", (int(user["id"]),)) as cursor:
        rows = await cursor.fetchall()
    items = []
    for row in rows:
        if await ranks.can(db, int(row[0]), int(user["id"]), "purge"):
            items.append({"id": int(row[0]), "title": str(row[1] or "Чат")[:160]})
    return {"items": items}


@router.get("/chats/{cid}")
async def current(cid: int, page: int = Query(0, ge=0, le=10000), mode: str = Query("pending", pattern="^(pending|decided|all)$"),
                  db=Depends(get_db), user=Depends(require_tg_user)):
    await _authorize(db, user, cid, reading=True)
    return await flow.view(db, chat_id=cid, page=page, mode=mode)


@router.post("/chats/{cid}/start")
async def start(cid: int, body: StartBody, db=Depends(get_db), user=Depends(require_tg_user)):
    await _authorize(db, user, cid)
    if body.date_to < body.date_from:
        raise HTTPException(400, "Конец периода раньше начала.")
    args = f"{body.norm} {bridge.fmt(body.date_from)}-{bridge.fmt(body.date_to)}"
    try:
        plan = bridge.plan_purge(args, local_now().date(), None)
        if isinstance(plan, str):
            raise flow.PurgeConflict(plan)
        targets = await bridge.find_violators(db, cid, plan)
        targets, _ = await bridge.screen_violators(get_bot(), db, cid, targets)
        dest = await admin_chat_of(db, cid) or cid
        async with db.execute("SELECT chat_title FROM chat_settings WHERE chat_id=?", (cid,)) as cursor:
            chat = await cursor.fetchone()
        receipt = await bridge.start_shared(get_bot(), db, cid, int(user["id"]), plan, targets, dest, action_id=body.action_id)
        sid, active = receipt["session_id"], receipt["active"]
        if receipt["created"]:
            asyncio.create_task(bridge._send_dossiers(get_bot(), sid, cid, str(chat[0] or "Чат") if chat else "Чат", dest, targets))
    except (flow.PurgeConflict, UsageError) as error:
        raise HTTPException(409, str(error))
    return {"ok": True, "session_id": sid, "active": active, "message": "Чистка началась. Решения можно принимать здесь или в Telegram." if active else "Этот запуск уже обработан, чистка завершена."}


@router.post("/chats/{cid}/decision")
async def decision(cid: int, body: DecisionBody, db=Depends(get_db), user=Depends(require_tg_user)):
    await _authorize(db, user, cid)
    try:
        return await bridge.decide_shared(get_bot(), db, cid, body.session_id, body.user_id,
                                         int(user["id"]), body.action, body.action_id)
    except flow.PurgeConflict as error:
        raise HTTPException(409, str(error))


@router.post("/chats/{cid}/finish")
async def finish(cid: int, body: FinishBody, db=Depends(get_db), user=Depends(require_tg_user)):
    await _authorize(db, user, cid, reading=True)
    try:
        result = await flow.complete(db, chat_id=cid, actor=int(user["id"]), expected_session=body.session_id)
    except flow.PurgeConflict as error:
        raise HTTPException(409, str(error))
    return {"ok": True, **result}


@router.post("/chats/{cid}/reconcile")
async def reconcile(cid: int, body: ReconcileBody, db=Depends(get_db), user=Depends(require_tg_user)):
    await _authorize(db, user, cid, reading=True)
    async def authorize(actual, target, action):
        if actual != cid:
            raise flow.PurgeConflict("Чистка относится к другому чату.")
        await bridge.authorize_shared(get_bot(), db, cid, int(user["id"]), action="read")
    async def materialize(row, applied):
        await bridge.materialize_reconciled(get_bot(), db, cid, row, applied=applied)
    try:
        return await flow.reconcile(db, session_id=body.session_id, user_id=body.user_id, actor=int(user["id"]),
                                    applied=body.applied, reason=body.reason, authorize=authorize, materialize=materialize)
    except flow.PurgeConflict as error:
        raise HTTPException(409, str(error))
