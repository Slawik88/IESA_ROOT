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


class ChallengeRequest(BaseModel):
    username: str
    stake: float
    chat_id: int


@router.post("/challenge")
async def challenge(body: ChallengeRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Вызвать игрока на дуэль по username."""
    from infrastructure.repositories.zoo import get_user_pets as _get_pets

    async with db.execute(
        "SELECT user_tg_id FROM users WHERE user_tg_username = ?", (body.username,)
    ) as c:
        target = await c.fetchone()
    if not target:
        raise HTTPException(404, f"Игрок @{body.username} не найден.")
    if target[0] == user["id"]:
        raise HTTPException(400, "Нельзя вызвать самого себя.")

    # Need at least one active pet with non-100 fatigue
    my_pets = await _get_pets(db, user["id"], placement="nursery")
    if not my_pets:
        raise HTTPException(400, "Нужен хотя бы один питомец в питомнике.")

    pet = my_pets[0]
    from services.duel import create_challenge
    ok, result = await create_challenge(
        db, user["id"], target[0], body.chat_id, body.stake, pet
    )
    if not ok:
        raise HTTPException(400, str(result))
    await db.commit()
    return {"ok": True, "duel_id": result.get("duel_id")}


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
