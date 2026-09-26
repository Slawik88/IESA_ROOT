"""Current VIP status and authenticated Zarniki purchase."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tg_user
from core.registry import VIP_PERKS_PITCH
from services.vip import (VIP_BADGES, VIP_PACKAGES, VipConflict, VipError, get_daily_status, get_preferences,
                          get_vip_info, get_vip_seniority_days, purchase_vip, set_preferences)

router = APIRouter(prefix="/vip", tags=["vip"])


def _tiers_payload() -> list[dict]:
    return [{"tier": "vip", "label": "VIP", "duration_days": days,
             "price_zarniki": price, "purchasable": True}
            for days, price in VIP_PACKAGES.items()]


@router.get("/status")
async def vip_status(db=Depends(get_db), user=Depends(require_tg_user)):
    info = await get_vip_info(db, user["id"])
    seniority = await get_vip_seniority_days(db, user["id"])
    preferences = await get_preferences(db, user_id=int(user["id"]))
    daily = await get_daily_status(db, user_id=int(user["id"]))
    if info:
        return {
            "active": True,
            "tier": info["tier"],
            "tier_label": info["tier_label"],
            "expires_at": info["expires_at"].isoformat(),
            "days_left": info["days_left"],
            "seniority_days": seniority,
            "seniority_months": seniority // 30,
            "perks": VIP_PERKS_PITCH,
            "tiers": _tiers_payload(),
            "purchase_retired": False,
            "badges": [{"id": key, "symbol": symbol} for key, symbol in VIP_BADGES.items()],
            "preferences": preferences,
            "daily_mission": daily,
        }
    return {
        "active": False,
        "tier": None,
        "tier_label": None,
        "expires_at": None,
        "days_left": 0,
        "seniority_days": seniority,
        "seniority_months": seniority // 30,
        "perks": VIP_PERKS_PITCH,
        "tiers": _tiers_payload(),
        "purchase_retired": False,
        "badges": [{"id": key, "symbol": symbol} for key, symbol in VIP_BADGES.items()],
        "preferences": preferences,
        "daily_mission": daily,
    }


class PurchaseVipRequest(BaseModel):
    package_days: int
    action_id: str = Field(min_length=1, max_length=96)


class VipPreferencesRequest(BaseModel):
    badge_id: str = Field(min_length=1, max_length=32)
    badge_position: str = Field(pattern="^(left|right|both|hidden)$")
    reminder_enabled: bool = True


@router.post("/purchase")
async def purchase_vip_endpoint(
    body: PurchaseVipRequest,
    db=Depends(get_db),
    user=Depends(require_tg_user),
):
    try:
        return await purchase_vip(
            db, user_id=int(user["id"]), package_days=body.package_days, action_id=body.action_id,
        )
    except (VipError, VipConflict) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.put("/preferences")
async def update_vip_preferences(
    body: VipPreferencesRequest, db=Depends(get_db), user=Depends(require_tg_user),
):
    try:
        return await set_preferences(
            db, user_id=int(user["id"]), badge_id=body.badge_id,
            badge_position=body.badge_position, reminder_enabled=body.reminder_enabled,
        )
    except (VipError, VipConflict) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
