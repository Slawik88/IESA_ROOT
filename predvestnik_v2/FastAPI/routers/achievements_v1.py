"""Read-only Mini App projection for durable long-horizon achievements."""
from fastapi import APIRouter, Depends

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.achievements_v1 import ensure_tables
from services import achievements_v1 as achievements


router = APIRouter(prefix="/achievements-v1", tags=["achievements-v1"])


@router.get("/me")
async def my_achievements(db=Depends(get_db), user=Depends(require_tg_user)):
    await ensure_tables(db)
    return await achievements.overview(db, user_id=int(user["id"]))
