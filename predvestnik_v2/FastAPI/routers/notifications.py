"""FastAPI/routers/notifications.py — отложенные веб-уведомления (Welcome Back)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories import web_notifications as wn

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/pending")
async def pending(db=Depends(get_db), user=Depends(require_tg_user)):
    """Непросмотренные уведомления, накопившиеся пока игрок был офлайн."""
    items = await wn.get_unseen(db, user["id"])
    return {"notifications": items}


class SeenRequest(BaseModel):
    ids: list[int] = []


@router.post("/seen")
async def seen(body: SeenRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Пометить показанные уведомления просмотренными."""
    await wn.mark_seen(db, user["id"], body.ids)
    await db.commit()
    return {"ok": True}
