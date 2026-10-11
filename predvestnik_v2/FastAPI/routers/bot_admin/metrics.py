"""Раздел «Метрики»: посещения мини-приложения, время на вкладках, команды бота, чаты."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from services import bot_metrics

router = APIRouter(prefix="/bot-admin/api", tags=["bot-admin"])
_user = section("metrics")


@router.get("/metrics")
async def metrics(days: int = 1, user=Depends(_user), db=Depends(get_db)):
    return await bot_metrics.dashboard(db, days)


@router.get("/metrics/export")
async def metrics_export(days: int = 1, user=Depends(_user), db=Depends(get_db)):
    """CSV за период; BOM, чтобы Excel открыл русские буквы."""
    body = "\ufeff" + await bot_metrics.export_csv(db, days if days in bot_metrics.PERIODS else 1)
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="metrics-{days}d.csv"'})
