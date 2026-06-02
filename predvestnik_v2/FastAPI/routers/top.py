"""FastAPI/routers/top.py — топ активности чата.
Использует те же функции stats-репозитория что и bot/handlers/stats.py.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from FastAPI.deps import get_db
from infrastructure.repositories.stats import get_top_messages, get_top_messages_for_dates
from infrastructure.repositories.streak import get_chat_timezone

router = APIRouter(prefix="/top", tags=["top"])


@router.get("/{chat_id}")
async def chat_top(
    chat_id: int,
    period: str = Query("all_time", pattern="^(day|week|all_time)$"),
    db=Depends(get_db),
):
    """Топ игроков чата. period: day | week | all_time."""
    if period == "all_time":
        rows = await get_top_messages(db, chat_id, "all_time", limit=50)
        return _fmt(rows, "msg_count")

    tz_offset = await get_chat_timezone(db, chat_id)
    now = datetime.now(timezone.utc) + timedelta(hours=tz_offset)
    today = now.strftime("%Y-%m-%d")

    if period == "day":
        rows = await get_top_messages_for_dates(db, chat_id, today, today, limit=50)
    else:
        week_start = (now - timedelta(days=6)).strftime("%Y-%m-%d")
        rows = await get_top_messages_for_dates(db, chat_id, week_start, today, limit=50)

    return _fmt(rows, "msg_count")


def _fmt(rows: list[dict], count_key: str) -> list[dict]:
    return [
        {
            "position": i + 1,
            "user_id":  r["user_tg_id"],
            "username": r["user_tg_username"] or f"ID{r['user_tg_id']}",
            "count":    r[count_key],
        }
        for i, r in enumerate(rows)
    ]
