"""Marks API: the player's own «Регалии» sheet (worn marks and earned ones still ahead)."""
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.streak import get_global_streak
from infrastructure.repositories.users import get_first_seen
from services import marks_v1 as marks

router = APIRouter(prefix="/marks-v1", tags=["marks-v1"])


@router.get("/me")
async def my_marks(db=Depends(get_db), user=Depends(require_tg_user)) -> dict:
    user_id = int(user["id"])
    try:
        streak = (await get_global_streak(db, user_id))["streak"]
        return await marks.sheet(db, user_id, streak=streak, joined=await get_first_seen(db, user_id))
    except Exception as exc:
        logger.exception("marks_v1 failed")
        raise HTTPException(status_code=500, detail="Регалии временно недоступны") from exc
