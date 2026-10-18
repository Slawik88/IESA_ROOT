"""Раздел «Промокоды»."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from bot.chat.global_ranks import CREATOR
from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from FastAPI.routers.bot_admin.safe import AdminRoute
from services import admin_people, admin_security, promo_v2

router = APIRouter(prefix="/bot-admin/api", tags=["bot-admin"], route_class=AdminRoute)
_user = section("promo")


def _fail(exc: promo_v2.PromoError):
    raise HTTPException(400, str(exc))


@router.get("/promo")
async def list_promo(q: str = "", user=Depends(_user), db=Depends(get_db)):
    return {"items": await promo_v2.list_codes(db, query=q)}


@router.get("/promo-options")
async def promo_options(user=Depends(_user), db=Depends(get_db)):
    rewards = [
        {"type": "mora", "title": "🪙 Мора", "field": "amount"},
        {"type": "diamonds", "title": "💎 Алмазы", "field": "amount"},
        {"type": "essence", "title": "🔮 Эссенция", "field": "amount"},
        *([{"type": "zarniki", "title": "✨ Зарники", "field": "amount"}] if user["rank"] >= CREATOR else []),
        {"type": "vip", "title": "👑 VIP, дней", "field": "days"},
        {"type": "skin", "title": "✨ Образ", "field": "id"},
    ]
    return {
        "rewards": rewards,
        "skins": promo_v2.skin_choices(),
        "private_skins": await promo_v2.private_skins_state(db),
    }


@router.get("/chats")
async def chats(q: str = "", user=Depends(_user), db=Depends(get_db)):
    q = q.strip()
    params: tuple = ()
    where = ""
    if q:
        where = "WHERE c.chat_title ILIKE ? OR CAST(c.chat_id AS TEXT) LIKE ?"
        params = (promo_v2.like_pattern(q), promo_v2.like_pattern(q))
    async with db.execute(f"SELECT c.chat_id, c.chat_title, l.admin_chat_id IS NOT NULL "
                          "FROM chat_settings c LEFT JOIN chat_links l ON l.admin_chat_id = c.chat_id "
                          f"{where} ORDER BY c.chat_title NULLS LAST LIMIT 30", params) as cur:
        return {"items": [{"id": int(r[0]), "title": r[1] or str(r[0]), "admin": bool(r[2])} for r in await cur.fetchall()]}


@router.post("/promo/preview")
async def preview_promo(data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    try:
        return await promo_v2.preview(db, data)
    except promo_v2.PromoError as exc:
        _fail(exc)


@router.post("/promo/bulk")
async def bulk_promo(data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    admin_security.rate_limit(user, "promo_bulk")
    try:
        made = await promo_v2.bulk_create(db, data, actor_id=user["id"])
    except promo_v2.PromoError as exc:
        _fail(exc)
    await admin_people.audit(db, user["id"], "promo_bulk", details={"count": len(made["codes"]), "first": made["codes"][0],
                                                                    "rewards": made["rewards_text"]})
    await admin_security.after_action(db, user, "promo_bulk")
    return made


@router.get("/promo/{code}")
async def get_promo(code: str, user=Depends(_user), db=Depends(get_db)):
    item = await promo_v2.get_code(db, code)
    if not item:
        raise HTTPException(404, "Промокод не найден.")
    return item


@router.post("/promo")
async def create_promo(data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    admin_security.rate_limit(user, "promo_create")
    try:
        saved = await promo_v2.save_code(db, data, actor_id=user["id"], create=True)
    except promo_v2.PromoError as exc:
        _fail(exc)
    await admin_people.audit(db, user["id"], "promo_create", details={"code": str(saved.get("code") or data.get("code") or "")})
    await admin_security.after_action(db, user, "promo_create")
    return saved


@router.put("/promo/{code}")
async def update_promo(code: str, data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    data = {**data, "code": code}
    admin_security.rate_limit(user, "promo_update")
    try:
        saved = await promo_v2.save_code(db, data, actor_id=user["id"], create=False)
    except promo_v2.PromoError as exc:
        _fail(exc)
    await admin_people.audit(db, user["id"], "promo_update", details={"code": code})
    await admin_security.after_action(db, user, "promo_update")
    return saved


@router.post("/promo/{code}/active")
async def toggle_promo(code: str, data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    try:
        result = await promo_v2.set_active(db, code, bool(data.get("active")), actor_id=user["id"])
    except promo_v2.PromoError as exc:
        _fail(exc)
    await admin_people.audit(db, user["id"], "promo_active", details={"code": code, "active": bool(data.get("active"))})
    return result
