"""FastAPI/routers/achievements.py — галерея достижений с прогресс-барами."""
from fastapi import APIRouter, Depends

from FastAPI.deps import get_db, require_tg_user
from core.registry import ACHIEVEMENTS, ACHIEVEMENT_LEVEL_REWARDS
from infrastructure.repositories.achievements import get_all_achievements

router = APIRouter(prefix="/achievements", tags=["achievements"])


@router.get("/")
async def my_achievements(db=Depends(get_db), user=Depends(require_tg_user)):
    """Все достижения с текущим прогрессом и наградами за следующий уровень."""
    progress = await get_all_achievements(db, user["id"])

    result = []
    for ach_id, meta in ACHIEVEMENTS.items():
        state = progress.get(ach_id, {"level": 0, "progress": 0.0})
        level = state["level"]
        current_progress = state["progress"]
        thresholds = meta["thresholds"]
        max_level = len(thresholds)

        next_threshold = thresholds[level] if level < max_level else None
        pct = min(100, round(current_progress / next_threshold * 100)) if next_threshold else 100

        next_reward = ACHIEVEMENT_LEVEL_REWARDS.get(level + 1) if level < 10 else None

        result.append({
            "id":              ach_id,
            "icon":            meta["icon"],
            "name":            meta["name"],
            "level":           level,
            "max_level":       max_level,
            "progress":        current_progress,
            "next_threshold":  next_threshold,
            "pct":             pct,
            "completed":       level >= max_level,
            "next_reward":     next_reward,
        })

    # Sort: in-progress first, then completed
    result.sort(key=lambda x: (x["completed"], -x["pct"]))
    return result
