"""Управление доступом владельцев чатов: выключатель и отзыв (только создатель)."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from FastAPI.routers.bot_admin.safe import AdminRoute
from bot.chat.global_ranks import CREATOR
from services import admin_people, admin_security, owner_access

router = APIRouter(prefix="/bot-admin/api/access", tags=["bot-admin"], route_class=AdminRoute)
_user = section("settings")


def _creator(user: dict) -> None:
    if user["rank"] < CREATOR:
        raise HTTPException(403, "Доступом владельцев чатов управляет только создатель.")


@router.get("/owners")
async def owners_state(user=Depends(_user), db=Depends(get_db)):
    _creator(user)
    return {"enabled": await owner_access.enabled(db), "blocked": await owner_access.blocked_list(db),
            "max_chats": owner_access.MAX_CHATS}


@router.post("/owners")
async def owners_toggle(data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    _creator(user)
    on = bool(data.get("enabled"))
    await owner_access.set_enabled(db, user["id"], on)
    await admin_people.audit(db, user["id"], "owner_access", details={"enabled": on})
    await admin_security.alert(db, f"{await admin_security._name(db, user['id'])}: вход владельцев чатов в админку "
                                   f"{'включён' if on else 'выключен'}.", skip=user["id"])
    return {"ok": True, "enabled": on}


@router.post("/owners/block")
async def owners_block(data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    _creator(user)
    try:
        uid = int(data.get("user_id"))
    except (TypeError, ValueError):
        raise HTTPException(400, "Нужен ID человека.")
    blocked = bool(data.get("blocked", True))
    await owner_access.set_blocked(db, user["id"], uid, blocked, str(data.get("reason") or ""))
    await admin_people.audit(db, user["id"], "owner_block", user_id=uid, details={"blocked": blocked})
    return {"ok": True, "blocked": blocked}
