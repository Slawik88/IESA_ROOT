"""FastAPI/routers/inventory.py — инвентарь: просмотр + взаимодействие с предметами."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.registry import ITEMS_REGISTRY, GACHA_RATES
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.economy import get_inventory, remove_item
from infrastructure.repositories.zoo import open_eggs_batch, grant_duplicate

router = APIRouter(prefix="/inventory", tags=["inventory"])

_CATEGORY_ORDER = {"egg": 0, "food": 1, "spin_token": 2, "booster": 3, "material": 4}


@router.get("/")
async def my_inventory(db=Depends(get_db), user=Depends(require_tg_user)):
    rows = await get_inventory(db, user["id"])
    result = []
    for row in rows:
        item = ITEMS_REGISTRY.get(row["item_id"], {})
        result.append({
            "item_id":     row["item_id"],
            "name":        item.get("name", row["item_id"]),
            "quantity":    row["quantity"],
            "category":    item.get("category", "unknown"),
            "description": item.get("description", ""),
            "spin_type":   item.get("spin_type"),       # for spin tokens
            "boost_hours": item.get("boost_hours"),     # for exp boosters
            "fatigue_restore": item.get("fatigue_restore"),  # for food
            "gacha_rates": GACHA_RATES.get(row["item_id"]),  # for eggs
        })
    result.sort(key=lambda x: (_CATEGORY_ORDER.get(x["category"], 9), x["item_id"]))
    return result


class OpenEggRequest(BaseModel):
    egg_id: str
    count: int = 1


@router.post("/open-egg")
async def open_egg(body: OpenEggRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Открыть яйцо из инвентаря."""
    count = max(1, min(body.count, 10))
    if body.egg_id not in GACHA_RATES:
        raise HTTPException(400, "Неизвестный тип яйца.")

    results = await open_eggs_batch(db, user["id"], body.egg_id, count, is_summoned=False)
    if results is None:
        raise HTTPException(400, "Нет яиц в инвентаре.")
    await db.commit()

    # Track achievements (same logic as bot/handlers/inventory.py)
    try:
        from services.achievements import increment_metric as _ach
        await _ach(db, user["id"], "eggs_opened", delta=float(count))
        new_species = sum(1 for r in results if r.get("outcome") == "first_copy_created")
        if new_species:
            await _ach(db, user["id"], "distinct_species_owned", delta=float(new_species))
        new_lv10 = sum(1 for r in results if r.get("new_level") == 10)
        if new_lv10:
            await _ach(db, user["id"], "pets_at_level_10", delta=float(new_lv10))
        await db.commit()
    except Exception:
        pass

    return {"ok": True, "results": results}


class ApplyDustRequest(BaseModel):
    dust_id: str
    pet_id: int


@router.post("/apply-dust")
async def apply_dust(body: ApplyDustRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Применить Звёздную пыль к питомцу (добавить дубликаты)."""
    dust_amounts = {"star_dust_s": 1, "star_dust_l": 5}
    amount = dust_amounts.get(body.dust_id)
    if not amount:
        raise HTTPException(400, "Не является звёздной пылью.")

    async with db.execute(
        "SELECT species_id, rarity FROM pets WHERE id = ? AND owner_id = ?",
        (body.pet_id, user["id"]),
    ) as c:
        pet = await c.fetchone()
    if not pet:
        raise HTTPException(404, "Питомец не найден.")

    ok = await remove_item(db, user["id"], body.dust_id, 1, commit=False)
    if not ok:
        raise HTTPException(400, "Нет пыли в инвентаре.")

    outcomes = [await grant_duplicate(db, user["id"], pet["species_id"]) for _ in range(amount)]
    await db.commit()
    return {"ok": True, "duplicates_added": amount, "outcomes": outcomes}
