"""FastAPI/routers/streak.py — стрик-календарь."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.streak import get_global_streak

router = APIRouter(prefix="/streak", tags=["streak"])


@router.get("/calendar")
async def streak_calendar(db=Depends(get_db), user=Depends(require_tg_user)):
    """Последние 60 дней активности для отрисовки календаря.
    Возвращает список {date, active: bool, message_count: int}.
    """
    now = datetime.now(timezone.utc)
    days = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(59, -1, -1)]

    async with db.execute(
        "SELECT date, SUM(message_count) AS cnt "
        "FROM daily_user_stats "
        "WHERE user_id = ? AND date >= ? "
        "GROUP BY date",
        (user["id"], days[0]),
    ) as c:
        rows = {r["date"]: r["cnt"] for r in await c.fetchall()}

    # Глобальный стрик (chat_id = 0) — единый источник правды, то же что бот
    streak_row = await get_global_streak(db, user["id"])

    return {
        "streak": streak_row["streak"],
        "calendar": [
            {"date": d, "active": d in rows, "count": rows.get(d, 0)}
            for d in days
        ],
    }
