"""FastAPI/routers/duels.py — дуэли: просмотр и управление."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from services.duel import decline_duel

router = APIRouter(prefix="/duels", tags=["duels"])


@router.get("/active")
async def active_duels(db=Depends(get_db), user=Depends(require_tg_user)):
    """Входящие вызовы на дуэль (где я — challenged) + исходящие."""
    async with db.execute(
        "SELECT d.id, d.challenger_id, d.challenged_id, d.stake, d.status, d.created_at, "
        "uc.user_tg_username AS challenger_name, ud.user_tg_username AS challenged_name "
        "FROM duels d "
        "LEFT JOIN users uc ON uc.user_tg_id = d.challenger_id "
        "LEFT JOIN users ud ON ud.user_tg_id = d.challenged_id "
        "WHERE (d.challenger_id = ? OR d.challenged_id = ?) AND d.status = 'pending' "
        "ORDER BY d.created_at DESC",
        (user["id"], user["id"]),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


@router.get("/history")
async def duel_history(db=Depends(get_db), user=Depends(require_tg_user)):
    """История дуэлей: последние 20."""
    async with db.execute(
        "SELECT d.id, d.challenger_id, d.challenged_id, d.stake, d.status, "
        "d.winner_id, d.created_at, d.resolved_at, "
        "uc.user_tg_username AS challenger_name, ud.user_tg_username AS challenged_name "
        "FROM duels d "
        "LEFT JOIN users uc ON uc.user_tg_id = d.challenger_id "
        "LEFT JOIN users ud ON ud.user_tg_id = d.challenged_id "
        "WHERE d.challenger_id = ? OR d.challenged_id = ? "
        "ORDER BY d.created_at DESC LIMIT 20",
        (user["id"], user["id"]),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


class DeclineRequest(BaseModel):
    duel_id: int


@router.post("/decline")
async def decline(body: DeclineRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Отклонить входящий вызов на дуэль."""
    async with db.execute(
        "SELECT id, challenged_id FROM duels WHERE id = ? AND status = 'pending'",
        (body.duel_id,),
    ) as c:
        duel = await c.fetchone()
    if not duel or duel["challenged_id"] != user["id"]:
        raise HTTPException(404, "Вызов не найден или уже недоступен.")

    ok = await decline_duel(db, body.duel_id)
    if not ok:
        raise HTTPException(400, "Не удалось отклонить вызов.")
    await db.commit()
    return {"ok": True}
