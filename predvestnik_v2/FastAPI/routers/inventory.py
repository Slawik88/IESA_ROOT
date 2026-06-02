"""FastAPI/routers/inventory.py — инвентарь игрока.
Читает из infrastructure/repositories/economy.py — та же функция что и у бота.
"""
from fastapi import APIRouter, Depends
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.economy import get_inventory
from core.registry import ITEMS_REGISTRY

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/")
async def my_inventory(db=Depends(get_db), user=Depends(require_tg_user)):
    """Полный инвентарь текущего пользователя."""
    rows = await get_inventory(db, user["id"])

    result = []
    for row in rows:
        item_def = ITEMS_REGISTRY.get(row["item_id"], {})
        result.append({
            "item_id":     row["item_id"],
            "name":        item_def.get("name", row["item_id"]),
            "quantity":    row["quantity"],
            "category":    item_def.get("category", "unknown"),
            "description": item_def.get("description", ""),
        })

    # Сортировка: яйца, еда, утилиты, остальное
    _ORDER = {"egg": 0, "food": 1, "utility": 2, "booster": 3, "spin_token": 4, "material": 5}
    result.sort(key=lambda x: (_ORDER.get(x["category"], 9), x["item_id"]))

    return result
