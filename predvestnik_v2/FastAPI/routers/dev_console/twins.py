"""dev_console/twins.py — твинк-детект: диагностика для разработчика, без банов.

Кнопка «Пересчитать» на сайте гоняет тяжёлый запрос по требованию (не фоном) —
GET просто отдаёт последний кэш в памяти процесса (см. services/twin_detection).
"""
from fastapi import APIRouter, Depends

from FastAPI.deps import get_db, require_tg_user
from FastAPI.routers.admin_avatar import avatar_url
from ._common import require_console_perm
from services import twin_detection

router = APIRouter()


@router.get("/twins")
async def dev_twins(db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "twin_detection_view")
    data = twin_detection.get_cached()
    # ADMPROFILE: фото и в твинк-детекте — глазами видно «это один и тот же человек».
    # Копия пар: кэш в памяти процесса не мутируем (его отдаёт и бот).
    pairs = [dict(p) for p in (data.get("pairs") or [])]
    for p in pairs:
        p["avatar_a"] = avatar_url(p.get("user_a"))
        p["avatar_b"] = avatar_url(p.get("user_b"))
    return {**data, "pairs": pairs}


@router.post("/twins/recalculate")
async def dev_twins_recalculate(db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "twin_detection_view")
    return await twin_detection.recalculate(db)
