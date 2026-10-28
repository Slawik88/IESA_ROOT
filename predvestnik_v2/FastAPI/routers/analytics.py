"""FastAPI/routers/analytics.py — трекинг посещений вкладок мини-аппа (БЛОК 35)."""
import os
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories import analytics as analytics_repo
from services import tab_time

router = APIRouter(prefix="/analytics", tags=["analytics"])

_DEVELOPER_ID = int(os.getenv("DEVELOPER_ID", "0") or 0)


class _TabEvent(BaseModel):
    tab: str
    session_id: str


class _TabDurationEvent(BaseModel):
    tab: str
    session_id: str
    delta_sec: int = 60


@router.post("/tab")
async def track_tab(body: _TabEvent, db=Depends(get_db), user=Depends(require_tg_user)):
    if _DEVELOPER_ID and user["id"] == _DEVELOPER_ID:
        return {"ok": True}
    tab = (body.tab or "")[:64]
    sid = (body.session_id or "")[:64]
    if tab and sid:
        await analytics_repo.record_visit(db, user["id"], tab, sid)
    return {"ok": True}


@router.post("/tab-duration")
async def track_tab_duration(body: _TabDurationEvent, user=Depends(require_tg_user)):
    """Хартбит удержания: фронт копит видимые секунды вкладки и шлёт их раз в минуту и при сворачивании (БЛОК 36, S04).
    Сервер складывает их в памяти и пишет пачкой (services/tab_time.py): сам запрос в таблицу визитов не пишет."""
    if _DEVELOPER_ID and user["id"] == _DEVELOPER_ID:
        return {"ok": True}
    tab = (body.tab or "")[:64]
    sid = (body.session_id or "")[:64]
    delta = max(0, min(int(body.delta_sec or 0), analytics_repo.HEARTBEAT_MAX_DELTA))
    if tab and sid and delta:
        tab_time.add(int(user["id"]), tab, sid, delta)
    return {"ok": True}
