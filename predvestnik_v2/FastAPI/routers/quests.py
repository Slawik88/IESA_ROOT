"""FastAPI/routers/quests.py — ежедневные задания."""
from fastapi import APIRouter, Depends
from FastAPI.deps import get_db, require_tg_user
from services.quests import get_or_assign_quests

router = APIRouter(prefix="/quests", tags=["quests"])


@router.get("/{chat_id}")
async def daily_quests(chat_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    """Квесты пользователя в конкретном чате на сегодня."""
    quests = await get_or_assign_quests(db, user["id"], chat_id)
    return quests
