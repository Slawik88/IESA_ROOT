"""FastAPI/routers/vip.py — статус и покупка VIP-подписки (Implementation Block 2.5)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from core.registry import VIP_TIERS, ITEMS_REGISTRY
from services.vip import get_vip_info, get_vip_seniority_days, purchase_vip

router = APIRouter(prefix="/vip", tags=["vip"])


def _resolve_items(items: tuple) -> list[dict]:
    return [
        {"item_id": item_id, "name": ITEMS_REGISTRY.get(item_id, {}).get("name", item_id), "qty": qty}
        for item_id, qty in items
    ]


def _tiers_payload() -> list[dict]:
    return [
        {
            "tier": tier,
            "label": info["label"],
            "duration_days": info["duration_days"],
            "price_zarniki": info["price_zarniki"],
            "base_price_zarniki": info.get("base_price_zarniki", info["price_zarniki"]),
            "savings_zarniki": info.get("base_price_zarniki", info["price_zarniki"]) - info["price_zarniki"],
            "gift_mora": info["gift"].get("mora", 0),
            "gift_diamonds": info["gift"].get("diamonds", 0),
            "gift_items": _resolve_items(info["gift"].get("items", ())),
            "weekly": _resolve_items(info["weekly"]),
            "extra_slots": info.get("extra_slots", 0),
        }
        for tier, info in VIP_TIERS.items()
    ]


@router.get("/status")
async def vip_status(db=Depends(get_db), user=Depends(require_tg_user)):
    info = await get_vip_info(db, user["id"])
    seniority = await get_vip_seniority_days(db, user["id"])
    if info:
        return {
            "active": True,
            "tier": info["tier"],
            "tier_label": info["tier_label"],
            "expires_at": info["expires_at"].isoformat(),
            "days_left": info["days_left"],
            "seniority_days": seniority,
            "seniority_months": seniority // 30,
            "tiers": _tiers_payload(),
        }
    return {
        "active": False,
        "tier": None,
        "tier_label": None,
        "expires_at": None,
        "days_left": 0,
        "seniority_days": seniority,
        "seniority_months": seniority // 30,
        "tiers": _tiers_payload(),
    }


class PurchaseVipRequest(BaseModel):
    tier: str


@router.post("/purchase")
async def purchase_vip_endpoint(body: PurchaseVipRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    if body.tier not in VIP_TIERS:
        raise HTTPException(status_code=400, detail="Неизвестный тариф VIP.")

    ok, message = await purchase_vip(db, user["id"], body.tier)
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    await db.commit()
    return {"ok": True, "message": message}
