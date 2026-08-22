"""Read-only legacy duel history and safe release of pending wagers."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from services.duel import LEGACY_DUEL_CLOSED_MESSAGE, decline_duel

router = APIRouter(prefix="/duels", tags=["duels"])


@router.get("/active")
async def active_duels(db=Depends(get_db), user=Depends(require_tg_user)):
    """Pending legacy holds that either participant may release."""
    async with db.execute(
        "SELECT d.id, d.challenger_id, d.challenged_id, d.stake, d.status, d.created_at, "
        "uc.user_tg_username AS challenger_name, ud.user_tg_username AS challenged_name, "
        "(vc.user_id IS NOT NULL) AS challenger_is_vip, "
        "(vd.user_id IS NOT NULL) AS challenged_is_vip "
        "FROM duels d "
        "LEFT JOIN users uc ON uc.user_tg_id = d.challenger_id "
        "LEFT JOIN users ud ON ud.user_tg_id = d.challenged_id "
        "LEFT JOIN vip_subscriptions vc ON vc.user_id = d.challenger_id AND vc.expires_at > NOW() "
        "LEFT JOIN vip_subscriptions vd ON vd.user_id = d.challenged_id AND vd.expires_at > NOW() "
        "WHERE (d.challenger_id = ? OR d.challenged_id = ?) AND d.status = 'pending' "
        "ORDER BY d.created_at DESC",
        (user["id"], user["id"]),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


@router.get("/history")
async def duel_history(db=Depends(get_db), user=Depends(require_tg_user)):
    """Preserved results for the Legacy Hall; never creates new rewards."""
    async with db.execute(
        "SELECT d.id, d.challenger_id, d.challenged_id, d.stake, d.status, "
        "d.winner_id, d.winner_gain, d.commission, d.created_at, d.resolved_at, "
        "uc.user_tg_username AS challenger_name, ud.user_tg_username AS challenged_name, "
        "(vc.user_id IS NOT NULL) AS challenger_is_vip, "
        "(vd.user_id IS NOT NULL) AS challenged_is_vip "
        "FROM duels d "
        "LEFT JOIN users uc ON uc.user_tg_id = d.challenger_id "
        "LEFT JOIN users ud ON ud.user_tg_id = d.challenged_id "
        "LEFT JOIN vip_subscriptions vc ON vc.user_id = d.challenger_id AND vc.expires_at > NOW() "
        "LEFT JOIN vip_subscriptions vd ON vd.user_id = d.challenged_id AND vd.expires_at > NOW() "
        "WHERE d.challenger_id = ? OR d.challenged_id = ? "
        "ORDER BY d.created_at DESC LIMIT 20",
        (user["id"], user["id"]),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


class ChallengeRequest(BaseModel):
    username: str
    stake: float
    chat_id: int


@router.post("/challenge", status_code=410)
async def challenge(body: ChallengeRequest, user=Depends(require_tg_user)):
    """Hard stop: legacy CP wagers are not part of the clicker combat system."""
    raise HTTPException(410, LEGACY_DUEL_CLOSED_MESSAGE)


class DuelRequest(BaseModel):
    duel_id: int


async def _owned_pending(db, duel_id: int, user_id: int) -> bool:
    async with db.execute(
        "SELECT 1 FROM duels WHERE id = ? AND status = 'pending' "
        "AND (challenger_id = ? OR challenged_id = ?)",
        (duel_id, user_id, user_id),
    ) as cursor:
        return bool(await cursor.fetchone())


@router.post("/accept", status_code=410)
async def accept(body: DuelRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """An old Accept action releases the hold; it never resolves a CP battle."""
    if not await _owned_pending(db, body.duel_id, user["id"]):
        raise HTTPException(404, "Вызов не найден или уже закрыт.")
    await decline_duel(db, body.duel_id)
    raise HTTPException(410, LEGACY_DUEL_CLOSED_MESSAGE)


@router.post("/decline")
async def decline(body: DuelRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Either participant can release a pending legacy hold."""
    if not await _owned_pending(db, body.duel_id, user["id"]):
        raise HTTPException(404, "Вызов не найден или уже закрыт.")
    if not await decline_duel(db, body.duel_id):
        raise HTTPException(409, "Ставка уже освобождена.")
    return {"ok": True, "message": "Старая ставка освобождена."}
