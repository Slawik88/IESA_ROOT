"""Раздел «Промокоды»."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from services import admin_people, promo_v2

router = APIRouter(prefix="/bot-admin/api", tags=["bot-admin"])
_user = section("promo")


def _fail(exc: promo_v2.PromoError):
    raise HTTPException(400, str(exc))


@router.get("/promo")
async def list_promo(q: str = "", user=Depends(_user), db=Depends(get_db)):
    return {"items": await promo_v2.list_codes(db, query=q)}


@router.get("/promo-options")
async def promo_options(user=Depends(_user)):
    return {
        "rewards": [
            {"type": "mora", "title": "🪙 Мора", "field": "amount"},
            {"type": "diamonds", "title": "💎 Алмазы", "field": "amount"},
            {"type": "essence", "title": "🔮 Эссенция", "field": "amount"},
            {"type": "vip", "title": "👑 VIP, дней", "field": "days"},
            {"type": "skin", "title": "✨ Образ", "field": "id"},
        ],
        "skins": promo_v2.skin_choices(),
        "private_skins": promo_v2.private_skins(),
    }


@router.get("/chats")
async def chats(q: str = "", user=Depends(_user), db=Depends(get_db)):
    q = q.strip()
    params: tuple = ()
    where = ""
    if q:
        where = "WHERE chat_title ILIKE ? OR CAST(chat_id AS TEXT) LIKE ?"
        params = (f"%{q}%", f"%{q}%")
    async with db.execute(f"SELECT chat_id, chat_title FROM chat_settings {where} "
                          "ORDER BY chat_title NULLS LAST LIMIT 30", params) as cur:
        return {"items": [{"id": int(r[0]), "title": r[1] or str(r[0])} for r in await cur.fetchall()]}


@router.get("/promo/{code}")
async def get_promo(code: str, user=Depends(_user), db=Depends(get_db)):
    item = await promo_v2.get_code(db, code)
    if not item:
        raise HTTPException(404, "Промокод не найден.")
    return item


@router.post("/promo")
async def create_promo(data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    try:
        saved = await promo_v2.save_code(db, data, actor_id=user["id"], create=True)
    except promo_v2.PromoError as exc:
        _fail(exc)
    await admin_people.audit(db, user["id"], "promo_create", details={"code": str(saved.get("code") or data.get("code") or "")})
    return saved


@router.put("/promo/{code}")
async def update_promo(code: str, data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    data = {**data, "code": code}
    try:
        saved = await promo_v2.save_code(db, data, actor_id=user["id"], create=False)
    except promo_v2.PromoError as exc:
        _fail(exc)
    await admin_people.audit(db, user["id"], "promo_update", details={"code": code})
    return saved


@router.post("/promo/{code}/active")
async def toggle_promo(code: str, data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    try:
        result = await promo_v2.set_active(db, code, bool(data.get("active")), actor_id=user["id"])
    except promo_v2.PromoError as exc:
        _fail(exc)
    await admin_people.audit(db, user["id"], "promo_active", details={"code": code, "active": bool(data.get("active"))})
    return result
