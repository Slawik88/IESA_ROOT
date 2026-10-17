"""Inventory API: the player's own stock (keys, pet food and cards, jokers, pets found, items kept from the previous game). Read-only."""
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories import system_flags
from services import inventory_v1 as inventory

router = APIRouter(prefix="/inventory-v1", tags=["inventory-v1"])


@router.get("/me")
async def my_inventory(db=Depends(get_db), user=Depends(require_tg_user)) -> dict:
    try:
        return await inventory.overview(
            db, int(user["id"]),
            chests=await system_flags.is_enabled(db, "content_chests_v1"),
            trail=await system_flags.is_enabled(db, "pets_v2"),
        )
    except Exception as exc:
        logger.exception("inventory_v1 failed")
        raise HTTPException(status_code=500, detail="Инвентарь временно недоступен") from exc
