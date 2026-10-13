"""Управление доступом владельцев чатов: выключатель и отзыв (только создатель)."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from FastAPI.routers.bot_admin.safe import AdminRoute
from bot.chat.global_ranks import CREATOR, bot_rank_name
from FastAPI.routers.bot_admin.auth import SECTIONS
from FastAPI.routers.bot_admin.people import ACTIONS
from services import admin_access, admin_people, admin_security, owner_access

router = APIRouter(prefix="/bot-admin/api/access", tags=["bot-admin"], route_class=AdminRoute)
_user = section("access")


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


# ── Права ролей: порог «минимальная роль» на раздел и действие, только то, что разрешено менять ──

def _items() -> list[dict]:
    out = []
    for key in sorted(admin_access.CONFIGURABLE):
        kind, name = key.split(":", 1)
        title, default = (SECTIONS[name][0], SECTIONS[name][1]) if kind == "section" else (ACTIONS[name][0], ACTIONS[name][1])
        out.append({"key": key, "group": "section" if kind == "section" else "moderation", "title": title, "default": default})
    return out


def _role_word(rank: int) -> str:
    return bot_rank_name(rank).split(" ", 1)[-1].lower()


@router.get("/matrix")
async def matrix(user=Depends(_user), db=Depends(get_db)):
    _creator(user)
    grants = await admin_access.load_grants(db)
    items = [{**i, "current": admin_access.effective_min(i["key"], i["default"], grants), "changed": i["key"] in grants}
             for i in _items()]
    return {"items": items, "floor": admin_access.FLOOR, "ceiling": admin_access.CEILING,
            "roles": [{"rank": r, "name": bot_rank_name(r)} for r in range(admin_access.FLOOR, admin_access.CEILING + 1)]}


@router.post("/matrix")
async def matrix_set(data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    """Порог на одно право. `min_rank: null` возвращает значение по умолчанию. Подтверждение: название новой роли (или «сброс»)."""
    _creator(user)
    key = str(data.get("key") or "")
    item = next((i for i in _items() if i["key"] == key), None)
    if not item:
        raise HTTPException(400, "Это право закреплено в коде и не настраивается.")
    raw = data.get("min_rank")
    new = None if raw in (None, "") else int(raw)
    if new is not None and not admin_access.FLOOR <= new <= admin_access.CEILING:
        raise HTTPException(400, f"Порог — от {admin_access.FLOOR} до {admin_access.CEILING}.")
    word = "сброс" if new is None else _role_word(new)
    if str(data.get("confirm") or "").strip().lower() != word:
        raise HTTPException(400, f"Для подтверждения введите «{word}».")
    old = admin_access.effective_min(key, item["default"], await admin_access.load_grants(db))
    await admin_access.set_grant(db, user, key, new)
    shown = item["default"] if new is None else new
    await admin_security.alert(db, f"{await admin_security._name(db, user['id'])} изменил права: «{item['title']}» теперь с роли "
                                   f"«{bot_rank_name(shown)}» (было «{bot_rank_name(old)}»).", skip=user["id"])
    return {"ok": True, "current": shown}
