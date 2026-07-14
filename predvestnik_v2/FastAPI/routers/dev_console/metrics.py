"""dev_console/metrics.py — аналитика посещаемости для разработчика (БЛОК 35)."""
from fastapi import APIRouter, Depends

from FastAPI.deps import get_db, require_tg_user
from ._common import require_console_perm
from infrastructure.repositories import analytics as analytics_repo

router = APIRouter()


@router.get("/analytics")
async def dev_analytics(db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "metrics_view")
    return await analytics_repo.get_dashboard(db)
