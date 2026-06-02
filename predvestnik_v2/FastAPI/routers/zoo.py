"""FastAPI/routers/zoo.py — питомцы: просмотр, кормление, экспедиции, управление."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.constants import (
    PET_PLACEMENT_FATIGUE_RESTORE,
    get_pet_bonus, get_level_for_duplicates, get_total_duplicates_for_level,
    PET_LEVEL_MILESTONE_REWARDS,
)
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


@router.get("/pet/{pet_id}")
async def pet_detail(pet_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    """Полная информация о питомце: бонусы по уровням, дубликаты, прогресс."""
    async with db.execute(
        "SELECT * FROM pets WHERE id = ? AND owner_id = ?",
        (pet_id, user["id"]),
    ) as c:
        row = await c.fetchone()
    if not row:
        raise HTTPException(404, "Питомец не найден.")

    pet = dict(row)
    species = PET_SPECIES.get(pet["species_id"], {})
    rarity = pet.get("rarity", "common")
    level = pet.get("pet_level", 1)
    dups = pet.get("duplicates_collected", 0)

    # Build level progression table
    levels = []
    for lv in range(1, 11):
        bonus = get_pet_bonus(pet["species_id"], lv)
        dups_needed_total = get_total_duplicates_for_level(rarity, lv)
        dups_for_next = (
            get_total_duplicates_for_level(rarity, lv + 1) - dups_needed_total
            if lv < 10 else None
        )
        milestone = PET_LEVEL_MILESTONE_REWARDS.get(lv)
        levels.append({
            "level": lv,
            "unlocked": lv <= level,
            "current": lv == level,
            "bonus": bonus,
            "dups_total_required": dups_needed_total,
            "dups_for_this_level": dups_for_next,
            "milestone": milestone,
        })

    # Duplicates needed to reach next level
    dups_for_next_level = (
        get_total_duplicates_for_level(rarity, level + 1) - dups
        if level < 10 else 0
    )

    food = {
        fid: {"name": ITEMS_REGISTRY[fid]["name"], "qty": qty,
              "restore": ITEMS_REGISTRY[fid]["fatigue_restore"]}
        for fid in _FOOD_IDS
        if (qty := await get_item_quantity(db, user["id"], fid)) > 0
    }

    return {
        **pet,
        "species_name": species.get("name", pet["species_id"]),
        "species_desc": species.get("desc", ""),
        "current_bonus": get_pet_bonus(pet["species_id"], level),
        "dups_for_next_level": max(0, dups_for_next_level),
        "levels": levels,
        "available_food": food,
    }


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
    """Справочник всех видов питомцев с бонусами по уровням."""
    result = []
    for sid, info in PET_SPECIES.items():
        # Build readable bonus table for levels 1, 4, 8, 10 (tier breakpoints)
        bonus_tiers = {}
        for lv in [1, 4, 8, 10]:
            bonus_tiers[str(lv)] = get_pet_bonus(sid, lv)
        result.append({
            "species_id":  sid,
            "name":        info["name"],
            "rarity":      info["rarity"],
            "role":        info["default_role"],
            "desc":        info["desc"],
            "bonus_tiers": bonus_tiers,
        })
    return result


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
    return {"ok": True, "fatigue_before": pet["fatigue"], "fatigue_after": new_fatigue,
            "restored": item["fatigue_restore"]}


class BoostRequest(BaseModel):
    pet_id: int
    booster_id: str


@router.post("/boost")
async def boost_expedition(body: BoostRequest, db=Depends(get_db), user=Depends(require_tg_user)):
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
    placement: str


@router.post("/move")
async def move_pet(body: MoveRequest, db=Depends(get_db), user=Depends(require_tg_user)):
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
