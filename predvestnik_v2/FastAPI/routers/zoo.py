"""FastAPI/routers/zoo.py — питомцы: просмотр, кормление, экспедиции, управление."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.constants import PET_PLACEMENT_FATIGUE_RESTORE
from core.registry import ITEMS_REGISTRY, PET_SPECIES
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.economy import get_item_quantity, remove_item
from infrastructure.repositories.zoo import get_user_pets

router = APIRouter(prefix="/zoo", tags=["zoo"])

_FOOD_IDS = ["food_basic", "food_elite", "food_energy", "food_super", "food_diamond"]
_PLACEMENTS = ("active", "passive", "storage")


@router.get("/")
async def my_zoo(db=Depends(get_db), user=Depends(require_tg_user)):
    """Все питомцы + доступная еда."""
    pets = await get_user_pets(db, user["id"])
    food = {
        fid: {"name": ITEMS_REGISTRY[fid]["name"], "qty": qty,
              "restore": ITEMS_REGISTRY[fid]["fatigue_restore"]}
        for fid in _FOOD_IDS
        if (qty := await get_item_quantity(db, user["id"], fid)) > 0
    }
    return {"pets": pets, "available_food": food}


@router.get("/expeditions")
async def active_expeditions(db=Depends(get_db), user=Depends(require_tg_user)):
    """Активные экспедиции с доступными ускорителями."""
    async with db.execute(
        "SELECT e.pet_id, e.duration_hours, e.ends_at, p.name, p.species_id "
        "FROM active_expeditions e JOIN pets p ON e.pet_id = p.id "
        "WHERE p.owner_id = ?",
        (user["id"],),
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]

    boosters = {
        bid: {"name": ITEMS_REGISTRY[bid]["name"],
              "boost_hours": ITEMS_REGISTRY[bid]["boost_hours"],
              "qty": await get_item_quantity(db, user["id"], bid)}
        for bid in ("exp_boost_1h", "exp_boost_2h", "exp_boost_4h")
        if (await get_item_quantity(db, user["id"], bid)) > 0
    }
    return {"expeditions": rows, "boosters": boosters}


@router.get("/species")
async def species_encyclopedia():
    """Справочник всех видов питомцев."""
    return [
        {"species_id": sid, "name": info["name"], "rarity": info["rarity"],
         "role": info["default_role"], "desc": info["desc"]}
        for sid, info in PET_SPECIES.items()
    ]


class FeedRequest(BaseModel):
    pet_id: int
    food_id: str


@router.post("/feed")
async def feed_pet(body: FeedRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    if body.food_id not in _FOOD_IDS:
        raise HTTPException(400, "Неизвестный тип еды.")
    item = ITEMS_REGISTRY[body.food_id]

    async with db.execute(
        "SELECT id, fatigue FROM pets WHERE id = ? AND owner_id = ?",
        (body.pet_id, user["id"]),
    ) as c:
        pet = await c.fetchone()
    if not pet:
        raise HTTPException(404, "Питомец не найден.")

    ok = await remove_item(db, user["id"], body.food_id, 1, commit=False)
    if not ok:
        raise HTTPException(400, f"Нет {item['name']} в инвентаре.")

    new_fatigue = max(0, pet["fatigue"] - item["fatigue_restore"])
    await db.execute("UPDATE pets SET fatigue = ? WHERE id = ?", (new_fatigue, body.pet_id))
    await db.commit()
    return {"ok": True, "fatigue_before": pet["fatigue"], "fatigue_after": new_fatigue}


class BoostRequest(BaseModel):
    pet_id: int
    booster_id: str


@router.post("/boost")
async def boost_expedition(body: BoostRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Ускорить экспедицию ускорителем из инвентаря."""
    item = ITEMS_REGISTRY.get(body.booster_id, {})
    boost_hours = item.get("boost_hours", 0)
    if not boost_hours:
        raise HTTPException(400, "Не является ускорителем.")

    async with db.execute(
        "SELECT e.pet_id FROM active_expeditions e "
        "JOIN pets p ON e.pet_id = p.id "
        "WHERE e.pet_id = ? AND p.owner_id = ?",
        (body.pet_id, user["id"]),
    ) as c:
        if not await c.fetchone():
            raise HTTPException(404, "Экспедиция не найдена.")

    ok = await remove_item(db, user["id"], body.booster_id, 1, commit=False)
    if not ok:
        raise HTTPException(400, "Ускоритель не найден в инвентаре.")

    await db.execute(
        f"UPDATE active_expeditions "
        f"SET ends_at = GREATEST(NOW(), ends_at - ({boost_hours} * INTERVAL '1 hour')) "
        f"WHERE pet_id = ?",
        (body.pet_id,),
    )
    await db.commit()
    return {"ok": True, "boosted_hours": boost_hours}


class MoveRequest(BaseModel):
    pet_id: int
    placement: str   # active | passive | storage


@router.post("/move")
async def move_pet(body: MoveRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Переместить питомца между активным/пассивным/складом."""
    if body.placement not in _PLACEMENTS:
        raise HTTPException(400, "Допустимые значения: active, passive, storage.")

    async with db.execute(
        "SELECT id, placement FROM pets WHERE id = ? AND owner_id = ?",
        (body.pet_id, user["id"]),
    ) as c:
        pet = await c.fetchone()
    if not pet:
        raise HTTPException(404, "Питомец не найден.")

    entering_nursery = body.placement in ("active", "passive")
    if entering_nursery:
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            "UPDATE pets SET placement = ?, "
            "fatigue = LEAST(100, fatigue + ?), "
            "last_fatigue_update = ? WHERE id = ?",
            (body.placement, PET_PLACEMENT_FATIGUE_RESTORE, now_str, body.pet_id),
        )
    else:
        await db.execute("UPDATE pets SET placement = ? WHERE id = ?",
                         (body.placement, body.pet_id))
    await db.commit()
    return {"ok": True, "placement": body.placement}
