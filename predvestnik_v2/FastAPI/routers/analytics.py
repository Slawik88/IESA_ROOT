"""FastAPI/routers/analytics.py — трекинг посещений вкладок мини-аппа (БЛОК 35)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories import analytics as analytics_repo

router = APIRouter(prefix="/analytics", tags=["analytics"])


class _TabEvent(BaseModel):
    tab: str
    session_id: str


@router.post("/tab")
async def track_tab(body: _TabEvent, db=Depends(get_db), user=Depends(require_tg_user)):
    tab = (body.tab or "")[:32]
    sid = (body.session_id or "")[:64]
    if tab and sid:
        await analytics_repo.record_visit(db, user["id"], tab, sid)
    return {"ok": True}
