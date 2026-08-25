"""FastAPI/routers/craft.py — крафт предметов."""
from fastapi import APIRouter, Depends, HTTPException
from FastAPI.deps import get_db, require_tg_user
from services.craft import get_craftable_list, craft

router = APIRouter(prefix="/craft", tags=["craft"])


@router.get("/")
async def craftable(db=Depends(get_db), user=Depends(require_tg_user)):
    """Preserved recipe catalogue; no new crafting in economy v3."""
    return {
        "retired": True,
        "recipes": [],
        "message": "Старый крафт закрыт. Материалы сохранены и не расходуются.",
    }


@router.post("/{recipe_id}")
async def do_craft(recipe_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    raise HTTPException(410, "Старый крафт закрыт. Материалы сохранены и не расходуются.")
