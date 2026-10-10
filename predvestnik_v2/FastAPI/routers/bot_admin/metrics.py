"""Раздел «Метрики»: посещения мини-приложения, время на вкладках, команды бота, чаты."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from services import bot_metrics

router = APIRouter(prefix="/bot-admin/api", tags=["bot-admin"])
_user = section("metrics")


@router.get("/metrics")
async def metrics(days: int = 1, user=Depends(_user), db=Depends(get_db)):
    return await bot_metrics.dashboard(db, days)
