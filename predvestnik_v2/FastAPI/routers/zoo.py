"""FastAPI/routers/zoo.py — питомцы: просмотр, кормление, экспедиции."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from core.registry import ITEMS_REGISTRY
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.economy import get_item_quantity, remove_item
from infrastructure.repositories.zoo import get_user_pets

router = APIRouter(prefix="/zoo", tags=["zoo"])

_FOOD_IDS = ["food_basic", "food_elite", "food_energy", "food_super", "food_diamond"]


@router.get("/")
async def my_zoo(db=Depends(get_db), user=Depends(require_tg_user)):
    """Питомцы пользователя с балансом усталости и доступной едой."""
    pets = await get_user_pets(db, user["id"])

    # Доступная еда в инвентаре — один запрос для всех
    food = {}
    for fid in _FOOD_IDS:
        qty = await get_item_quantity(db, user["id"], fid)
        if qty > 0:
            item = ITEMS_REGISTRY[fid]
            food[fid] = {"name": item["name"], "qty": qty, "restore": item["fatigue_restore"]}

    return {"pets": pets, "available_food": food}


@router.get("/expeditions")
async def active_expeditions(db=Depends(get_db), user=Depends(require_tg_user)):
    """Активные экспедиции питомцев."""
    async with db.execute(
        "SELECT e.pet_id, e.duration_hours, e.ends_at, p.name, p.species_id "
        "FROM active_expeditions e JOIN pets p ON e.pet_id = p.id "
        "WHERE p.owner_id = ?",
        (user["id"],),
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]
    return rows


class FeedRequest(BaseModel):
    pet_id: int
    food_id: str


@router.post("/feed")
async def feed_pet(body: FeedRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Покормить питомца выбранной едой."""
    if body.food_id not in _FOOD_IDS:
        raise HTTPException(400, "Неизвестный тип еды.")

    item = ITEMS_REGISTRY.get(body.food_id, {})
    restore = item.get("fatigue_restore", 0)

    # Проверяем принадлежность питомца
    async with db.execute(
        "SELECT id, fatigue FROM pets WHERE id = ? AND owner_id = ?",
        (body.pet_id, user["id"]),
    ) as c:
        pet = await c.fetchone()
    if not pet:
        raise HTTPException(404, "Питомец не найден.")

    ok = await remove_item(db, user["id"], body.food_id, 1, commit=False)
    if not ok:
        raise HTTPException(400, f"Нет {item.get('name', body.food_id)} в инвентаре.")

    new_fatigue = max(0, pet["fatigue"] - restore)
    await db.execute("UPDATE pets SET fatigue = ? WHERE id = ?", (new_fatigue, body.pet_id))
    await db.commit()

    return {"ok": True, "fatigue_before": pet["fatigue"], "fatigue_after": new_fatigue, "restored": restore}
