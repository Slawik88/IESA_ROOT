"""dev_console/skins.py: give and take back personal (exclusive) skins. A personal skin is not sold and not shown in the shop; the console gives it
to one chosen player at tier D, the player is told with a gift notification, and every change needs a reason and lands in the console log."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories import admin_log
from services import skins_v3 as skins

from ._common import _send_admin_gift, require_console_perm

router = APIRouter()


class SkinGiftRequest(BaseModel):
    user_id: int
    skin_id: str = Field(min_length=1, max_length=40)
    reason: str = Field(default="", max_length=200)


@router.get("/skins")
async def dev_skins(db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "skins_gift")
    return await skins.exclusive_view(db)


@router.post("/skins/grant")
async def dev_skins_grant(body: SkinGiftRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "skins_gift")
    try:
        name = await skins.grant_exclusive(db, body.user_id, body.skin_id, body.reason)
    except skins.SkinConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    await admin_log.add(db, user["id"], body.user_id, "skin", f"+ {name}", 1.0, body.reason, 0.0, 1.0)
    await db.commit()
    await _send_admin_gift(db, body.user_id, [{"label": f"Личный образ «{name}»", "amount": 1, "kind": "skin", "skin_id": body.skin_id}], body.reason)
    await db.commit()
    return {"ok": True, "message": f"Образ «{name}» выдан: тир D, игроку пришло уведомление."}


@router.post("/skins/revoke")
async def dev_skins_revoke(body: SkinGiftRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "skins_gift")
    try:
        name = await skins.revoke_exclusive(db, body.user_id, body.skin_id, body.reason)
    except skins.SkinConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    await admin_log.add(db, user["id"], body.user_id, "skin", f"- {name}", -1.0, body.reason, 1.0, 0.0)
    await db.commit()
    return {"ok": True, "message": f"Образ «{name}» отозван."}
