"""dev_console/broadcast.py — Рассылка по чатам с фильтром аудитории."""
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories import routing as routing_repo
from ._common import _require_dev, _tg_call

router = APIRouter()


# ── 7. Рассылка по чатам (с фильтром аудитории) ──────────────────────────────────
_BROADCAST_AUDIENCES = {"all", "main", "admin", "main_admin", "dm", "dm_admin"}


class BroadcastRequest(BaseModel):
    text: str
    audience: str = "all"   # all | main | admin | main_admin | dm | dm_admin


@router.get("/broadcast/audience-counts")
async def dev_broadcast_counts(db=Depends(get_db), user=Depends(require_tg_user)):
    """Сколько чатов получит рассылку по каждому фильтру — для превью перед отправкой."""
    _require_dev(user)
    return {a: len(await routing_repo.get_broadcast_targets(db, a))
            for a in _BROADCAST_AUDIENCES}


@router.post("/broadcast")
async def dev_broadcast(body: BroadcastRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Пустой текст.")
    audience = body.audience if body.audience in _BROADCAST_AUDIENCES else "all"
    chat_ids = await routing_repo.get_broadcast_targets(db, audience)
    sent = failed = 0
    for cid in chat_ids:
        r = await _tg_call("sendMessage", chat_id=cid, text=text, parse_mode="HTML")
        if r.get("ok"):
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)
    return {"ok": True, "sent": sent, "failed": failed,
            "total": len(chat_ids), "audience": audience}
