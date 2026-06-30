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
    """Дневные + недельные квесты пользователя + статусы супер-наград за комплишен (БЛОК 5)."""
    quests = await get_or_assign_quests(db, user["id"], chat_id)
    bonus = await daily_bonus_status(db, user["id"], chat_id)
    weekly = await get_or_assign_weekly_quests(db, user["id"], chat_id)
    weekly_bonus = await weekly_bonus_status(db, user["id"], chat_id)
    return {"quests": quests, "bonus": bonus, "weekly": weekly, "weekly_bonus": weekly_bonus}
