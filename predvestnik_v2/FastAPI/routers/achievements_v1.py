"""Read-only Mini App projection for durable long-horizon achievements and chat-bot achievements."""
from fastapi import APIRouter, Depends

from bot.chat import achievements as chat_achievements
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.achievements_v1 import ensure_tables
from services import achievements_v1 as achievements


router = APIRouter(prefix="/achievements-v1", tags=["achievements-v1"])


@router.get("/me")
async def my_achievements(db=Depends(get_db), user=Depends(require_tg_user)):
    await ensure_tables(db)
    return await achievements.overview(db, user_id=int(user["id"]))


@router.get("/chat")
async def my_chat_achievements(db=Depends(get_db), user=Depends(require_tg_user)):
    """Chat-bot achievements (messages, warps, family, games) — read-only, no level writes or payouts."""
    await chat_achievements.ensure_schema(db)
    return await chat_achievements.overview(db, int(user["id"]))


@router.post('/reconcile')
async def reconcile_my_achievements(db=Depends(get_db), user=Depends(require_tg_user)):
    """Project only the authenticated player's verified history, never client counters."""
    await ensure_tables(db)
    await achievements.reconcile_history(db, user_id=int(user['id']))
    return await achievements.overview(db, user_id=int(user['id']))
