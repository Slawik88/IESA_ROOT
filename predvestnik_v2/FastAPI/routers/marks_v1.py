"""Marks API: the player's own «all marks» sheet (worn marks and earned ones still ahead)."""
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
        async with db.execute("SELECT COALESCE(global_rank, 0) FROM users WHERE user_tg_id=?", (user_id,)) as c:
            row = await c.fetchone()
        async with db.execute("SELECT COALESCE(SUM(user_messages_count_all_time), 0) FROM user_chat_stats WHERE user_tg_id=?", (user_id,)) as c:
            messages = int((await c.fetchone())[0])
        streak = (await get_global_streak(db, user_id))["streak"]
        return await marks.sheet(db, user_id, global_rank=int(row[0]) if row else 0, streak=streak, joined=await get_first_seen(db, user_id), messages=messages)
    except Exception as exc:
        logger.exception("marks_v1 failed")
        raise HTTPException(status_code=500, detail="Метки временно недоступны") from exc
