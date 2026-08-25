"""FastAPI/routers/quests.py — ежедневные задания."""
from fastapi import APIRouter, Depends
from FastAPI.deps import get_db, require_tg_user, require_module
from services.quests import (
    get_or_assign_quests, daily_bonus_status,
    get_or_assign_weekly_quests, weekly_bonus_status,
)

router = APIRouter(prefix="/quests", tags=["quests"], dependencies=[Depends(require_module("module_quests"))])


@router.get("/{chat_id}")
async def daily_quests(chat_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    """Terminal read response: old quest assignment must not create new rewards."""
    del chat_id, db, user
    return {
        "retired": True,
        "message": "Старые задания закрыты. Сохранённый прогресс показан только для истории.",
        "quests": [],
        "bonus": {"retired": True},
        "weekly": [],
        "weekly_bonus": {"retired": True},
    }
