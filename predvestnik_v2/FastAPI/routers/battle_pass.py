"""FastAPI/routers/battle_pass.py — статус и получение наград Боевого пропуска (Implementation Block 5.7)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from core.constants import BATTLE_PASS_XP_PER_LEVEL
from core.registry import BATTLE_PASS_REWARDS, ITEMS_REGISTRY
from core.themes import THEMES
from services.battle_pass import (
    claim_reward, get_active_season, get_progress, level_status, refresh_seasons_cache,
)

router = APIRouter(prefix="/battle_pass", tags=["battle_pass"])


def _resolve_items(items: tuple) -> list[dict]:
    return [
        {"item_id": item_id, "name": ITEMS_REGISTRY.get(item_id, {}).get("name", item_id), "qty": qty}
        for item_id, qty in items
    ]


def _reward_payload(reward: dict, level: int, track: str, progress: dict) -> dict:
    payload = {
        "mora": reward.get("mora", 0),
        "diamonds": reward.get("diamonds", 0),
        "items": _resolve_items(reward.get("items", ())),
        "status": level_status(level, track, progress),
    }
    theme_id = reward.get("theme")
    if theme_id:
        payload["theme"] = THEMES.get(theme_id, {}).get("name", theme_id)
    return payload


@router.get("/status")
async def battle_pass_status(db=Depends(get_db), user=Depends(require_tg_user)):
    # Подхватываем сезоны, созданные через Консоль разработчика (БД-кэш процесса)
    await refresh_seasons_cache(db)
    season = get_active_season()
    if not season:
        return {"active": False}

    progress = await get_progress(db, user["id"])
    rewards = []
    for lv in range(1, progress["max_level"] + 1):
        r = BATTLE_PASS_REWARDS.get(lv, {})
        rewards.append({
            "level": lv,
            "free": _reward_payload(r.get("free", {}), lv, "free", progress),
            "paid": _reward_payload(r.get("paid", {}), lv, "paid", progress),
        })

    return {
        "active": True,
        "season_label": season["label"],
        "level": progress["level"],
        "xp": progress["xp"],
        "xp_in_level": progress["xp_in_level"],
        "xp_to_next": progress["xp_to_next"],
        "xp_per_level": BATTLE_PASS_XP_PER_LEVEL,
        "max_level": progress["max_level"],
        "paid_track_open": progress["paid_track_open"],
        "rewards": rewards,
    }


class ClaimRequest(BaseModel):
    level: int
    track: str


@router.post("/claim")
async def battle_pass_claim(body: ClaimRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, message = await claim_reward(db, user["id"], body.level, body.track)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    await db.commit()
    return {"ok": True, "message": message}
