"""FastAPI/routers/events.py — активные игровые события."""
from fastapi import APIRouter, Depends

from FastAPI.deps import get_db, require_tg_user
from core.registry import ITEMS_REGISTRY

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/")
async def active_events(db=Depends(get_db), user=Depends(require_tg_user)):
    del db, user
    return {
        "retired": True,
        "message": "Старые случайные события закрыты. Текущая активность — Разлом колокола.",
        "exchange_retired": True,
        "daily_deals": [],
        "gacha_types": [],
    }
