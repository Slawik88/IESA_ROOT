"""FastAPI/routers/craft.py — крафт предметов."""
from fastapi import APIRouter, Depends, HTTPException
from FastAPI.deps import get_db, require_tg_user
from services.craft import get_craftable_list, craft

router = APIRouter(prefix="/craft", tags=["craft"])


@router.get("/")
async def craftable(db=Depends(get_db), user=Depends(require_tg_user)):
    """Рецепты с количеством ингредиентов у пользователя."""
    return await get_craftable_list(db, user["id"])


@router.post("/{recipe_id}")
async def do_craft(recipe_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    """Скрафтить предмет по рецепту."""
    result = await craft(db, user["id"], recipe_id)
    if not result["ok"]:
        raise HTTPException(400, result["reason"])
    await db.commit()
    return result
