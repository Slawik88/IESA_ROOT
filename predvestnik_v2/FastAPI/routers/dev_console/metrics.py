"""dev_console/metrics.py — аналитика посещаемости для разработчика (БЛОК 35)."""
from fastapi import APIRouter, Depends

from FastAPI.deps import get_db, require_tg_user
from ._common import _require_dev
from infrastructure.repositories import analytics as analytics_repo

router = APIRouter()


@router.get("/analytics")
async def dev_analytics(db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    return await analytics_repo.get_dashboard(db)
