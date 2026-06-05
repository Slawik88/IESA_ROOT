"""FastAPI/routers/zoo.py — питомцы: просмотр, кормление, экспедиции, управление."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.constants import (
    PET_PLACEMENT_FATIGUE_RESTORE,
    get_pet_bonus, get_level_for_duplicates, get_total_duplicates_for_level,
    PET_LEVEL_MILESTONE_REWARDS, HAMSTER_BONUSES,
)
from core.registry import ITEMS_REGISTRY, PET_SPECIES
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.economy import get_item_quantity, remove_item, add_balance
from infrastructure.repositories.zoo import (
    get_user_pets, get_nursery_count, get_zoo_stats, expand_max_slots, get_active_count,
    get_pending_hamster_income, get_active_species_level,
)
from services.zoo import get_active_wolf_food_extra

router = APIRouter(prefix="/zoo", tags=["zoo"])

_FOOD_IDS = ["food_basic", "food_elite", "food_energy", "food_super", "food_diamond"]
_PLACEMENTS = ("active", "passive", "storage")


@router.get("/")
async def my_zoo(db=Depends(get_db), user=Depends(require_tg_user)):
    """Все питомцы + доступная еда + статистика слотов."""
    pets = await get_user_pets(db, user["id"])
    stats = await get_zoo_stats(db, user["id"])
    slot_expander_qty = await get_item_quantity(db, user["id"], "slot_expander")
    food = {
        fid: {"name": ITEMS_REGISTRY[fid]["name"], "qty": qty,
              "restore": ITEMS_REGISTRY[fid]["fatigue_restore"]}
        for fid in _FOOD_IDS
        if (qty := await get_item_quantity(db, user["id"], fid)) > 0
    }
    pending_mora = await get_pending_hamster_income(db, user["id"])
    return {
        "pets": pets,
        "available_food": food,
        "max_slots": stats["max_slots"],
        "slot_expander_qty": slot_expander_qty,
        "pending_hamster_mora": round(pending_mora),
    }


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

    wolf_extra = await get_active_wolf_food_extra(db, user["id"])
    restore = item["fatigue_restore"] + wolf_extra
    new_fatigue = max(0, pet["fatigue"] - restore)
    await db.execute("UPDATE pets SET fatigue = ? WHERE id = ?", (new_fatigue, body.pet_id))

    # food_super: restore −5 fatigue to all other nursery pets
    if body.food_id == "food_super":
        await db.execute(
            "UPDATE pets SET fatigue = GREATEST(0, fatigue - 5) "
            "WHERE owner_id = ? AND placement IN ('active', 'passive') AND id != ?",
            (user["id"], body.pet_id),
        )

    await db.commit()

    # Quest: pet_feeds_today
    try:
        from services.quests import increment_metric as _q_incr
        async with db.execute(
            "SELECT chat_tg_id FROM user_chat_stats WHERE user_tg_id = ? "
            "ORDER BY user_messages_count_all_time DESC LIMIT 1",
            (user["id"],),
        ) as _cc:
            _cr = await _cc.fetchone()
        if _cr:
            await _q_incr(db, user["id"], _cr[0], "pet_feeds_today", delta=1.0)
            await db.commit()
    except Exception:
        pass

    return {"ok": True, "fatigue_before": pet["fatigue"], "fatigue_after": new_fatigue,
            "restored": restore, "wolf_extra": wolf_extra}


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
    currently_in_nursery = pet["placement"] in ("active", "passive")

    if entering_nursery and not currently_in_nursery:
        # Проверяем лимит общих слотов питомника
        stats = await get_zoo_stats(db, user["id"])
        occupied = await get_nursery_count(db, user["id"])
        if occupied >= stats["max_slots"]:
            raise HTTPException(
                400,
                f"Питомник заполнен ({occupied}/{stats['max_slots']} слотов). "
                f"Используй 🏡 Расширитель слота, чтобы добавить слот."
            )

    # Проверяем лимит активных питомцев (макс 1)
    if body.placement == "active" and pet["placement"] != "active":
        active_now = await get_active_count(db, user["id"])
        if active_now >= 1:
            raise HTTPException(
                400,
                "У тебя уже есть активный питомец. Сначала переведи его в пассивный или склад."
            )

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


@router.post("/expand-slot")
async def expand_slot(db=Depends(get_db), user=Depends(require_tg_user)):
    """Применить 🏡 Расширитель слота из инвентаря → +1 слот питомника (макс 6)."""
    qty = await get_item_quantity(db, user["id"], "slot_expander")
    if qty < 1:
        raise HTTPException(400, "🏡 Расширитель слота не найден в инвентаре.")

    new_slots = await expand_max_slots(db, user["id"])
    if new_slots == 0:
        raise HTTPException(400, "Питомник уже расширен до максимума (6 слотов).")

    ok = await remove_item(db, user["id"], "slot_expander", 1, commit=False)
    if not ok:
        raise HTTPException(400, "Не удалось списать расширитель.")

    await db.commit()
    return {"ok": True, "max_slots": new_slots}


@router.post("/collect")
async def collect_hamster(db=Depends(get_db), user=Depends(require_tg_user)):
    """Собрать накопленную Мору от Хомяков-банкиров."""
    import random
    from datetime import datetime as _dt

    stats = await get_zoo_stats(db, user["id"])

    async with db.execute(
        "SELECT COALESCE(pet_level,1) AS pet_level, fatigue FROM pets "
        "WHERE owner_id = ? AND species_id = 'hamster' AND placement IN ('active','passive')",
        (user["id"],),
    ) as c:
        hamster_rows = [dict(r) for r in await c.fetchall()]

    productive = [
        h for h in hamster_rows
        if h["fatigue"] < 100
        or HAMSTER_BONUSES.get(max(1, min(10, h["pet_level"])), {}).get("ignore_exhaustion", False)
    ]

    if not productive:
        raise HTTPException(400, "В Питомнике нет бодрствующих Хомяков-банкиров.")

    accumulated = await get_pending_hamster_income(db, user["id"])
    if accumulated < 1:
        raise HTTPException(400, "Хомяки ещё не накопили Мору. Попробуйте через несколько минут.")

    double_mora_bonus = 0
    diamond_bonus = 0.0
    today_str = _dt.now().strftime("%Y-%m-%d")
    last_collect_day = (stats.get("last_income_collection") or "")[:10]

    for h in productive:
        b = HAMSTER_BONUSES.get(max(1, min(10, h["pet_level"])), {})
        if b.get("double_chance", 0.0) > 0 and random.random() < b["double_chance"]:
            double_mora_bonus += int(accumulated / max(1, len(productive)))
        if b.get("daily_diamond", 0.0) > 0 and last_collect_day != today_str:
            diamond_bonus = max(diamond_bonus, b["daily_diamond"])

    dragon_level = await get_active_species_level(db, user["id"], "dragon")
    dragon_bonus_mora = (
        int(get_pet_bonus("dragon", dragon_level).get("hamster_collect_bonus", 0.0))
        if dragon_level > 0 else 0
    )

    total_mora = int(accumulated) + double_mora_bonus + dragon_bonus_mora

    await add_balance(db, user["id"], mora=total_mora, diamonds=diamond_bonus,
                      commit=False, source="hamster_collect")
    now_str = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
    await db.execute(
        "UPDATE user_zoo_stats SET last_income_collection = ? WHERE user_id = ?",
        (now_str, user["id"]),
    )
    await db.commit()

    return {
        "ok": True,
        "mora": total_mora,
        "diamonds": diamond_bonus,
        "double_bonus": double_mora_bonus,
        "dragon_bonus": dragon_bonus_mora,
    }
