"""FastAPI/routers/exchange.py — обмен Моры → Алмазы во время ивента."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.constants import EXCHANGE_RATE_MORA_PER_DIAMOND, EXCHANGE_DAILY_CAP_DIAMONDS
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories.exchange import (
    get_active_event, get_scheduled_event, get_user_quota, add_quota,
)

router = APIRouter(prefix="/exchange", tags=["exchange"])


@router.get("/")
async def exchange_status(db=Depends(get_db), user=Depends(require_tg_user)):
    """Статус ивента обмена + остаток квоты пользователя."""
    active = await get_active_event(db)
    if not active:
        scheduled = await get_scheduled_event(db)
        return {"active": False, "scheduled": dict(scheduled) if scheduled else None}

    event = dict(active)
    used = await get_user_quota(db, user["id"], event["id"])
    bal = await eco_repo.get_balance(db, user["id"])
    return {
        "active":     True,
        "event":      event,
        "rate":       EXCHANGE_RATE_MORA_PER_DIAMOND,
        "daily_cap":  EXCHANGE_DAILY_CAP_DIAMONDS,
        "used_today": used,
        "remaining":  max(0.0, EXCHANGE_DAILY_CAP_DIAMONDS - used),
        "mora":       float(bal["user_balance_mora"] or 0),
        "diamonds":   float(bal["user_balance_diamonds"] or 0),
    }


class ConvertRequest(BaseModel):
    diamonds: float


@router.post("/convert")
async def convert(body: ConvertRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Обменять Мору на Алмазы. Работает только пока ивент активен."""
    active = await get_active_event(db)
    if not active:
        raise HTTPException(400, "Ивент обмена сейчас не активен.")

    event = dict(active)
    diamonds = round(body.diamonds, 2)
    if diamonds < 1:
        raise HTTPException(400, f"Минимум 1 💎.")

    used = await get_user_quota(db, user["id"], event["id"])
    remaining = EXCHANGE_DAILY_CAP_DIAMONDS - used
    if diamonds > remaining:
        raise HTTPException(400, f"Дневной лимит: {remaining:.1f} 💎 осталось.")

    mora_needed = diamonds * EXCHANGE_RATE_MORA_PER_DIAMOND
    bal = await eco_repo.get_balance(db, user["id"])
    if bal["user_balance_mora"] < mora_needed:
        raise HTTPException(400, f"Нужно {mora_needed:,.0f} 🪙, есть {bal['user_balance_mora']:,.0f}.")

    await eco_repo.add_balance(db, user["id"], mora=-mora_needed, diamonds=diamonds,
                               commit=False, source="exchange", note=str(event["id"]))
    await add_quota(db, user["id"], event["id"], diamonds)
    await db.commit()

    return {"ok": True, "mora_spent": mora_needed, "diamonds_gained": diamonds}
