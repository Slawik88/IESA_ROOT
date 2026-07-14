"""dev_console/broadcast.py — Рассылка по чатам с фильтром аудитории."""
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories import routing as routing_repo
from ._common import require_console_perm, _tg_call

router = APIRouter()


# ── 7. Рассылка по чатам (с фильтром аудитории) ──────────────────────────────────
_BROADCAST_AUDIENCES = {"all", "main", "admin", "main_admin", "dm", "dm_admin"}


class BroadcastRequest(BaseModel):
    text: str
    audience: str = "all"   # all | main | admin | main_admin | dm | dm_admin


@router.get("/broadcast/audience-counts")
async def dev_broadcast_counts(db=Depends(get_db), user=Depends(require_tg_user)):
    """Сколько чатов получит рассылку по каждому фильтру — для превью перед отправкой."""
    await require_console_perm(db, user, "broadcast_send")
    return {a: len(await routing_repo.get_broadcast_targets(db, a))
            for a in _BROADCAST_AUDIENCES}


@router.post("/broadcast/test")
async def dev_broadcast_test(body: BroadcastRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """admin_audit C2: тест-отправка рассылки СЕБЕ в ЛС — проверить
    форматирование/разметку до массовой отправки."""
    await require_console_perm(db, user, "broadcast_send")
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Пустой текст.")
    r = await _tg_call("sendMessage", chat_id=user["id"],
                       text="🧪 <b>ТЕСТ РАССЫЛКИ</b> (видите только вы)\n\n" + text,
                       parse_mode="HTML")
    if not r.get("ok"):
        raise HTTPException(400, f"Не доставлено: {r.get('description') or r.get('error') or '?'} "
                                 f"(ЛС с ботом открыты?)")
    return {"ok": True}


@router.post("/broadcast")
async def dev_broadcast(body: BroadcastRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "broadcast_send")
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
