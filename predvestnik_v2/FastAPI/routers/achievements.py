"""FastAPI/routers/achievements.py — галерея достижений с прогресс-барами."""
from fastapi import APIRouter, Depends

from FastAPI.deps import get_db, require_tg_user
from core.registry import ACHIEVEMENTS, ACHIEVEMENT_LEVEL_REWARDS
from infrastructure.repositories.achievements import get_all_achievements
from services.achievements import backfill_metric

router = APIRouter(prefix="/achievements", tags=["achievements"])


async def _backfill_snapshot_metrics(db, user_id: int) -> None:
    """Catch up metrics whose true value is recomputable from current DB state —
    covers players whose qualifying history predates these achievements."""
    async with db.execute(
        "SELECT COUNT(DISTINCT species_id) FROM pets WHERE owner_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()
    await backfill_metric(db, user_id, "distinct_species_owned", float(row[0] or 0))

    async with db.execute(
        "SELECT COUNT(*) FROM pets WHERE owner_id = ? AND pet_level = 10", (user_id,)
    ) as c:
        row = await c.fetchone()
    await backfill_metric(db, user_id, "pets_at_level_10", float(row[0] or 0))

    async with db.execute(
        "SELECT MAX(streak) FROM daily_login WHERE user_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()
    await backfill_metric(db, user_id, "max_streak_ever", float(row[0] or 0))

    async with db.execute(
        "SELECT user_balance_mora, user_balance_diamonds FROM users WHERE user_tg_id = ?", (user_id,)
    ) as c:
        bal = await c.fetchone()
    if bal:
        await backfill_metric(db, user_id, "peak_mora_balance", float(bal[0] or 0))
        await backfill_metric(db, user_id, "peak_diamonds_balance", float(bal[1] or 0))

    async with db.execute(
        "SELECT COALESCE(SUM(user_messages_count_all_time), 0) FROM user_chat_stats WHERE user_tg_id = ?",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    await backfill_metric(db, user_id, "messages_total_global", float(row[0] or 0))

    async with db.execute(
        "SELECT COUNT(*) FROM auction_lots WHERE seller_id = ? AND status = 'sold'", (user_id,)
    ) as c:
        row = await c.fetchone()
    await backfill_metric(db, user_id, "auction_sales", float(row[0] or 0))

    # Модник (косметика) и Покоритель Врат (PvE) — игроки покупали косметику /
    # побеждали во Вратах ДО введения ачивок; их прошлое считаемо из БД, засчитываем.
    async with db.execute(
        "SELECT COUNT(*) FROM user_cosmetics WHERE user_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()
    await backfill_metric(db, user_id, "cosmetics_bought", float(row[0] or 0))

    async with db.execute(
        "SELECT COUNT(*) FROM battles WHERE user_id = ? AND mode = 'gates' AND status = 'won'",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    await backfill_metric(db, user_id, "gates_battles_won", float(row[0] or 0))

    await db.commit()


@router.get("/")
async def my_achievements(db=Depends(get_db), user=Depends(require_tg_user)):
    """Все достижения с текущим прогрессом и наградами за следующий уровень."""
    await _backfill_snapshot_metrics(db, user["id"])

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
