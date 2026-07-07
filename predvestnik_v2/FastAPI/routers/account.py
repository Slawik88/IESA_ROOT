"""FastAPI/routers/account.py — admin_audit C1b: управление аккаунтом на сайте.

Восстановление доступно и «удалённому» аккаунту (гейт бана здесь ни при чём —
удаление ≠ бан), поэтому все ручки на require_tg_user_base + свои проверки.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user_base
from services import account_deletion as acc

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/deletion-status")
async def deletion_status(db=Depends(get_db), user=Depends(require_tg_user_base)):
    st = await acc.get_state(db, int(user["id"]))
    d = st["deletion"] or {}
    return {
        "deleted": bool(st["deleted_at"]),
        "delete_after_days": st["delete_after_days"],
        "process_status": d.get("status"),
        "cooling_until": str(d["cooling_until"]) if d.get("cooling_until") else None,
        "restore_deadline": str(d["restore_deadline"]) if d.get("restore_deadline") else None,
    }


class InactivityRequest(BaseModel):
    days: int


@router.post("/set-inactivity")
async def set_inactivity(body: InactivityRequest, db=Depends(get_db),
                         user=Depends(require_tg_user_base)):
    ok, msg = await acc.set_inactivity_days(db, int(user["id"]), body.days)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


@router.post("/delete/request")
async def delete_request(db=Depends(get_db), user=Depends(require_tg_user_base)):
    ok, msg = await acc.request_deletion(db, int(user["id"]))
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


class DeleteConfirmRequest(BaseModel):
    code: str
    phrase: str


@router.post("/delete/confirm")
async def delete_confirm(body: DeleteConfirmRequest, db=Depends(get_db),
                         user=Depends(require_tg_user_base)):
    ok, msg = await acc.confirm_deletion(db, int(user["id"]), body.code, body.phrase)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


@router.post("/delete/cancel")
async def delete_cancel(db=Depends(get_db), user=Depends(require_tg_user_base)):
    ok, msg = await acc.cancel_deletion(db, int(user["id"]))
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


@router.post("/restore")
async def account_restore(db=Depends(get_db), user=Depends(require_tg_user_base)):
    ok, msg = await acc.restore_account(db, int(user["id"]))
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}
