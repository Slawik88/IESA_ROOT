"""FastAPI/routers/marriage.py — брак и семейный банк."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.marriages import (
    get_user_marriage, family_bank_transaction,
)
from infrastructure.repositories.zoo import get_user_pets
from services.achievements import increment_metric as ach_incr

router = APIRouter(prefix="/marriage", tags=["marriage"])


async def _get_any_marriage(db, user_id: int) -> dict | None:
    """Find marriage in any chat for this user."""
    async with db.execute(
        "SELECT id, chat_id, user1_id, user1_name, user2_id, user2_name, "
        "marriage_date, family_balance FROM marriages "
        "WHERE user1_id = ? OR user2_id = ?",
        (user_id, user_id),
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


@router.get("/")
async def my_marriage(db=Depends(get_db), user=Depends(require_tg_user)):
    """Брак текущего пользователя + питомцы семьи + стаж."""
    m = await _get_any_marriage(db, user["id"])
    if not m:
        return {"married": False}

    partner_id = m["user2_id"] if m["user1_id"] == user["id"] else m["user1_id"]
    partner_name = m["user2_name"] if m["user1_id"] == user["id"] else m["user1_name"]

    # Family pets (marriage_id set on pets)
    async with db.execute(
        "SELECT id, name, species_id, rarity, placement, fatigue, "
        "COALESCE(pet_level,1) AS pet_level "
        "FROM pets WHERE marriage_id = ?",
        (m["id"],),
    ) as c:
        family_pets = [dict(r) for r in await c.fetchall()]

    # Marriage duration in days
    from datetime import datetime, timezone
    try:
        since = datetime.fromisoformat(str(m["marriage_date"]).replace(" ", "T"))
        since = since.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - since).days
    except Exception:
        days = 0

    # Backfill vow_keeper achievement if days > 0 and progress is 0
    try:
        from infrastructure.repositories.achievements import get_achievement, upsert_achievement
        rec = await get_achievement(db, user["id"], "vow_keeper")
        if (rec is None or rec["progress"] == 0) and days > 0:
            grants = await ach_incr(db, user["id"], "marriage_days_total", delta=float(days))
            if grants:
                await db.commit()
    except Exception:
        pass

    return {
        "married": True,
        "marriage_id": m["id"],
        "partner_id": partner_id,
        "partner_name": partner_name,
        "family_balance": float(m["family_balance"] or 0),
        "days": days,
        "family_pets": family_pets,
    }


class BankRequest(BaseModel):
    marriage_id: int
    amount: float
    action: str   # "deposit" | "withdraw"


@router.post("/bank")
async def family_bank(body: BankRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Депозит или вывод из семейного банка."""
    if body.action not in ("deposit", "withdraw"):
        raise HTTPException(400, "action: 'deposit' или 'withdraw'")
    ok, msg = await family_bank_transaction(db, body.marriage_id, user["id"],
                                            body.amount, body.action)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}
