"""Read-only gallery of legacy achievement progress."""
from fastapi import APIRouter, Depends

from FastAPI.deps import get_db, require_tg_user
from core.registry import ACHIEVEMENTS
from infrastructure.repositories.achievements import get_all_achievements

router = APIRouter(prefix="/achievements", tags=["achievements"])


@router.get("/")
async def my_achievements(db=Depends(get_db), user=Depends(require_tg_user)):
    """Return saved progress without backfill, mutation, or reward promises."""
    progress = await get_all_achievements(db, user["id"])
    result = []
    for ach_id, meta in ACHIEVEMENTS.items():
        state = progress.get(ach_id, {"level": 0, "progress": 0.0})
        level = int(state["level"] or 0)
        current = float(state["progress"] or 0)
        thresholds = meta["thresholds"]
        max_level = len(thresholds)
        next_threshold = thresholds[level] if level < max_level else None
        pct = min(100, round(current / next_threshold * 100)) if next_threshold else 100
        result.append({
            "id": ach_id,
            "icon": meta["icon"],
            "name": meta["name"],
            "level": level,
            "max_level": max_level,
            "progress": current,
            "next_threshold": next_threshold,
            "pct": pct,
            "completed": level >= max_level,
            "next_reward": None,
            "desc": meta.get("desc", ""),
        })

    result.sort(key=lambda item: (item["completed"], -item["pct"]))
    return {
        "retired": True,
        "message": "Достижения сохранены как история. Новые действия не меняют прогресс и не выдают награды.",
        "achievements": result,
    }
