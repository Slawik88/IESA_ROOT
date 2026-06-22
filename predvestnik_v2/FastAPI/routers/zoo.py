"""FastAPI/routers/zoo.py — питомцы: просмотр, кормление, экспедиции, управление."""
import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.constants import (
    PET_PLACEMENT_FATIGUE_RESTORE,
    get_pet_bonus, get_level_for_duplicates, get_total_duplicates_for_level,
    PET_LEVEL_MILESTONE_REWARDS, HAMSTER_BONUSES, WOLF_BONUSES, UNICORN_BONUSES,
)
from core.registry import ITEMS_REGISTRY, PET_SPECIES, EXPEDITIONS_DATA
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.economy import get_item_quantity, remove_item, add_balance, spend_mora
from infrastructure.repositories.zoo import (
    get_user_pets, get_nursery_count, get_zoo_stats, buy_pet_slot, get_slot_purchase_state,
    get_active_count, get_pending_hamster_income, get_active_species_level, apply_fatigue_decay,
    get_species_bonus, hamster_bonus,
)
from services.formatting import parse_dt
from services.vip import get_extra_pet_slots
from services.zoo import get_active_wolf_food_extra, get_wolf_fatigue_reduction

router = APIRouter(prefix="/zoo", tags=["zoo"])

_FOOD_IDS = ["food_basic", "food_fried", "food_elite", "food_stew", "food_energy", "food_feast", "food_super", "food_diamond"]
_PLACEMENTS = ("active", "passive", "storage")


@router.get("/")
async def my_zoo(db=Depends(get_db), user=Depends(require_tg_user)):
    """Все питомцы + доступная еда + статистика слотов."""
    await apply_fatigue_decay(db, user["id"])
    pets = await get_user_pets(db, user["id"])
    stats = await get_zoo_stats(db, user["id"])
    food = {
        fid: {"name": ITEMS_REGISTRY[fid]["name"], "qty": qty,
              "restore": ITEMS_REGISTRY[fid]["fatigue_restore"]}
        for fid in _FOOD_IDS
        if (qty := await get_item_quantity(db, user["id"], fid)) > 0
    }
    pending_mora = await get_pending_hamster_income(db, user["id"])

    today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Wolf Lv8+ restore ability status
    wolf_restore_info = None
    wolf_lv = await get_active_species_level(db, user["id"], "wolf")
    if wolf_lv >= 8:
        w_b = WOLF_BONUSES.get(max(1, min(10, wolf_lv)), {})
        max_uses = w_b.get("daily_restore_uses", 0)
        async with db.execute(
            "SELECT uses_left FROM player_buffs WHERE user_id = ? AND buff_type = ?",
            (user["id"], f"wolf_restore_{today_key}"),
        ) as c:
            row = await c.fetchone()
        uses_left = row["uses_left"] if row else max_uses
        wolf_restore_info = {"uses_left": uses_left, "max_uses": max_uses,
                             "restore_amount": w_b.get("daily_restore_amount", 30)}

    # Unicorn Lv4+ immunity ability status
    unicorn_ability_info = None
    uni_lv = await get_active_species_level(db, user["id"], "unicorn")
    if uni_lv >= 4:
        u_b = UNICORN_BONUSES.get(max(1, min(10, uni_lv)), {})
        async with db.execute(
            "SELECT 1 FROM player_buffs WHERE user_id = ? AND buff_type = ?",
            (user["id"], f"unicorn_immunity_{today_key}"),
        ) as c:
            used_today = await c.fetchone() is not None
        async with db.execute(
            "SELECT expires_at FROM player_buffs WHERE user_id = ? "
            "AND buff_type = 'unicorn_immunity' AND expires_at > NOW()",
            (user["id"],),
        ) as c:
            immune_row = await c.fetchone()
        unicorn_ability_info = {
            "available": not used_today,
            "immunity_hours": u_b.get("immunity_hours", 0),
            "active": immune_row is not None,
            "expires_at": str(immune_row[0]) if immune_row else None,
        }

    slot_state = get_slot_purchase_state(stats["max_slots"])
    vip_extra = await get_extra_pet_slots(db, user["id"])
    return {
        "pets": pets,
        "available_food": food,
        "max_slots": stats["max_slots"],
        "base_slots": slot_state["base_slots"],
        "bought_slots": slot_state["bought_slots"],
        "max_purchasable": slot_state["max_purchasable"],
        "slot_next_price": slot_state["next_price"],   # None если докуплено максимум
        "at_slot_cap": slot_state["at_cap"],
        "vip_extra_slot": vip_extra,
        "pending_hamster_mora": round(pending_mora),
        "wolf_restore": wolf_restore_info,
        "unicorn_ability": unicorn_ability_info,
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

    # Atomic: remove item + update expedition time to prevent double-boost race
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ? FOR UPDATE",
                (user["id"], body.booster_id),
            ) as c:
                inv_row = await c.fetchone()
            if not inv_row or inv_row[0] < 1:
                raise HTTPException(400, "Ускоритель не найден в инвентаре.")
            await db.execute(
                "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?",
                (user["id"], body.booster_id),
            )
            await db.execute(
                "DELETE FROM inventory WHERE user_id = ? AND item_id = ? AND quantity <= 0",
                (user["id"], body.booster_id),
            )
            await db.execute(
                f"UPDATE active_expeditions "
                f"SET ends_at = GREATEST(NOW() + INTERVAL '30 seconds', ends_at - ({boost_hours} * INTERVAL '1 hour')) "
                f"WHERE pet_id = ?",
                (body.pet_id,),
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "Ошибка применения ускорителя.")
    return {"ok": True, "boosted_hours": boost_hours}


@router.get("/expedition-options")
async def expedition_options(db=Depends(get_db), user=Depends(require_tg_user)):
    """Данные для лаунчера похода на сайте: длительности (базовые цена/награда/
    усталость), активный питомец (тот же, кого отправит /start-expedition),
    занятость (1 поход на игрока за раз) и баланс Моры. Точные значения (скидки
    вида, снижение усталости) считаются при старте/возвращении."""
    uid = user["id"]
    options = [
        {"hours": h, "cost": d["cost"], "min_m": d["min_m"], "max_m": d["max_m"],
         "min_xp": d["min_xp"], "max_xp": d["max_xp"], "fatigue": d["fatigue"]}
        for h, d in sorted(EXPEDITIONS_DATA.items())
    ]
    async with db.execute(
        "SELECT id, name, species_id, rarity, COALESCE(pet_level,1) AS pet_level, fatigue "
        "FROM pets WHERE owner_id = ? AND placement = 'active' ORDER BY id LIMIT 1",
        (uid,),
    ) as c:
        row = await c.fetchone()
    active_pet = dict(row) if row else None
    async with db.execute(
        "SELECT ae.ends_at, p.name FROM active_expeditions ae JOIN pets p ON ae.pet_id = p.id "
        "WHERE p.owner_id = ? AND ae.ends_at > NOW() ORDER BY ae.ends_at DESC LIMIT 1",
        (uid,),
    ) as c:
        busy_row = await c.fetchone()
    async with db.execute(
        "SELECT COALESCE(user_balance_mora, 0) FROM users WHERE user_tg_id = ?", (uid,),
    ) as c:
        m = await c.fetchone()
    return {
        "options": options,
        "active_pet": active_pet,
        "busy": busy_row is not None,
        "busy_until": str(busy_row[0])[:16] if busy_row else None,
        "busy_pet": busy_row[1] if busy_row else None,
        "mora": float(m[0]) if m else 0.0,
    }


class StartExpeditionRequest(BaseModel):
    hours: int


@router.post("/start-expedition")
async def start_expedition(body: StartExpeditionRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Отправить активного питомца в поход. Синхронизировано с bot/handlers/expeditions.py."""
    if body.hours not in EXPEDITIONS_DATA:
        raise HTTPException(400, "Доступная длительность: 2, 4, 6 или 8 часов.")

    exp_data = EXPEDITIONS_DATA[body.hours]
    user_id = user["id"]

    async with db.execute(
        "SELECT id, name, species_id, fatigue FROM pets "
        "WHERE owner_id = ? AND placement = 'active' ORDER BY id LIMIT 1",
        (user_id,),
    ) as c:
        pet = await c.fetchone()
    if not pet:
        raise HTTPException(400, "Нет активного питомца. Переведите питомца в статус Активный.")

    pet_id, pet_name, species_id, fatigue = pet["id"], pet["name"], pet["species_id"], pet["fatigue"]

    async with db.execute(
        "SELECT ae.ends_at FROM active_expeditions ae "
        "JOIN pets p ON ae.pet_id = p.id "
        "WHERE p.owner_id = ? AND ae.ends_at > NOW() LIMIT 1",
        (user_id,),
    ) as c:
        active_row = await c.fetchone()
    if active_row:
        raise HTTPException(400, f"Питомец уже в походе (вернётся {str(active_row[0])[:16]}).")

    # Wolf reduces expedition fatigue
    wolf_reduction = await get_wolf_fatigue_reduction(db, user_id)
    base_fatigue = exp_data["fatigue"] * (1.0 - wolf_reduction)

    # Dog bonuses: speed, cost reduction, zero fatigue chance, self fatigue reduction
    # Block 12: бонус с учётом слота (passive ×0.5)
    dog = await get_species_bonus(db, user_id, "dog")
    speed_reduction = 0.0
    expedition_cost_reduction = 0.0
    zero_fatigue_chance = 0.0
    if dog:
        speed_reduction = dog.get("speed_reduction", 0.0)
        expedition_cost_reduction = dog.get("expedition_cost_reduction", 0.0)
        zero_fatigue_chance = dog.get("zero_fatigue_chance", 0.0)
        if species_id == "dog":
            self_fatigue_reduction = dog.get("self_fatigue_reduction", 0.0)
            base_fatigue *= (1.0 - self_fatigue_reduction)

    expedition_fatigue = int(base_fatigue)
    if zero_fatigue_chance > 0 and random.random() < zero_fatigue_chance:
        expedition_fatigue = 0

    if fatigue + expedition_fatigue > 100:
        raise HTTPException(400, f"Питомец слишком устал ({fatigue}/100). Покормите его.")

    # Turtle + dog cost discounts
    actual_cost = exp_data["cost"]
    if actual_cost > 0:
        turtle_b = await get_species_bonus(db, user_id, "turtle")  # Block 12: с учётом слота
        combined_mult = 1.0
        if turtle_b:
            combined_mult *= (1.0 - turtle_b.get("expedition_discount", 0.0))
        if expedition_cost_reduction > 0:
            combined_mult *= (1.0 - expedition_cost_reduction)
        actual_cost = max(0, int(exp_data["cost"] * combined_mult))

    if actual_cost > 0:
        ok, err = await spend_mora(db, user_id, actual_cost, source="expedition",
                                   note=f"expedition_{body.hours}h")
        if not ok:
            raise HTTPException(400, f"Недостаточно Моры (нужно {actual_cost} 🪙).")

    duration_hours = body.hours * (1.0 - speed_reduction)

    try:
        async with db.connection.transaction():
            await db.execute(
                "INSERT INTO active_expeditions (pet_id, chat_id, duration_hours, cost_mora, ends_at) "
                "VALUES (?, ?, ?, ?, NOW() + (? * INTERVAL '1 hour'))",
                (pet_id, 0, body.hours, actual_cost, duration_hours),
            )
            await db.execute(
                "UPDATE pets SET fatigue = fatigue + ? WHERE id = ?",
                (expedition_fatigue, pet_id),
            )
    except Exception:
        if actual_cost > 0:
            await add_balance(db, user_id, mora=actual_cost)
        raise HTTPException(500, "Не удалось запустить экспедицию. Мора возвращена.")

    return {
        "ok": True,
        "pet_name": pet_name,
        "hours": body.hours,
        "duration_hours": round(duration_hours, 2),
        "fatigue_before": fatigue,
        "fatigue_after": min(100, fatigue + expedition_fatigue),
        "cost": actual_cost,
    }


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
        # Проверяем лимит общих слотов питомника (+ read-time VIP-бонус extra_slots)
        stats = await get_zoo_stats(db, user["id"])
        occupied = await get_nursery_count(db, user["id"])
        extra = await get_extra_pet_slots(db, user["id"])
        if occupied >= stats["max_slots"] + extra:
            raise HTTPException(
                400,
                f"Питомник заполнен ({occupied}/{stats['max_slots'] + extra} слотов). "
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
        # Wolf Lv10: movement_immunity — no fatigue penalty on placement
        w_lv = await get_active_species_level(db, user["id"], "wolf")
        wolf_immune = (
            WOLF_BONUSES.get(max(1, min(10, w_lv)), {}).get("movement_immunity", False)
            if w_lv > 0 else False
        )
        if wolf_immune:
            await db.execute(
                "UPDATE pets SET placement = ?, last_fatigue_update = ? WHERE id = ?",
                (body.placement, now_str, body.pet_id),
            )
        else:
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
    return {"ok": True, "placement": body.placement, "wolf_immunity_applied": entering_nursery and w_lv > 0 and WOLF_BONUSES.get(max(1,min(10,w_lv)),{}).get("movement_immunity",False) if entering_nursery else False}


@router.post("/buy-slot")
async def buy_slot(db=Depends(get_db), user=Depends(require_tg_user)):
    """Купить следующий слот питомника за алмазы (прогрессивная цена 5/15/30/50 💎)."""
    ok, msg, new_slots, price = await buy_pet_slot(db, user["id"])
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "max_slots": new_slots, "price_paid": price, "message": msg}


class WolfRestoreRequest(BaseModel):
    pet_id: int


@router.post("/wolf-restore")
async def wolf_restore(body: WolfRestoreRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Восстановить усталость питомца силой Волка Lv8+ (1-2 раза в день)."""
    from datetime import datetime as _dt

    wolf_lv = await get_active_species_level(db, user["id"], "wolf")
    if wolf_lv == 0:
        raise HTTPException(400, "Нет активного Волка в питомнике.")

    w_b = WOLF_BONUSES.get(max(1, min(10, wolf_lv)), {})
    max_uses = w_b.get("daily_restore_uses", 0)
    restore_amount = w_b.get("daily_restore_amount", 0)
    if max_uses == 0:
        raise HTTPException(400, "Волк должен быть Lv8+ для этой способности.")

    today_key = f"wolf_restore_{_dt.now().strftime('%Y-%m-%d')}"
    async with db.execute(
        "SELECT uses_left FROM player_buffs WHERE user_id = ? AND buff_type = ?",
        (user["id"], today_key),
    ) as c:
        row = await c.fetchone()
    uses_left = row["uses_left"] if row else max_uses
    if uses_left <= 0:
        raise HTTPException(400, f"Лимит восстановлений на сегодня исчерпан ({max_uses}/{max_uses}).")

    async with db.execute(
        "SELECT id, fatigue FROM pets WHERE id = ? AND owner_id = ?",
        (body.pet_id, user["id"]),
    ) as c:
        pet = await c.fetchone()
    if not pet:
        raise HTTPException(404, "Питомец не найден.")
    if pet["fatigue"] == 0:
        raise HTTPException(400, "Питомец не устал.")

    new_fatigue = max(0, pet["fatigue"] - restore_amount)
    await db.execute("UPDATE pets SET fatigue = ? WHERE id = ?", (new_fatigue, body.pet_id))

    await db.execute(
        "INSERT INTO player_buffs (user_id, buff_type, uses_left, expires_at) "
        "VALUES (?, ?, ?, NOW() + INTERVAL '2 days') "
        "ON CONFLICT (user_id, buff_type) DO UPDATE SET uses_left = player_buffs.uses_left - 1",
        (user["id"], today_key, max_uses - 1),
    )
    await db.commit()

    return {
        "ok": True,
        "fatigue_before": pet["fatigue"],
        "fatigue_after": new_fatigue,
        "restored": restore_amount,
        "uses_left": uses_left - 1,
        "max_uses": max_uses,
    }


@router.post("/unicorn-immunity")
async def unicorn_immunity(db=Depends(get_db), user=Depends(require_tg_user)):
    """Активировать иммунитет усталости Единорога Lv4+ (1 раз в день)."""
    from datetime import datetime as _dt, timedelta as _td

    uni_lv = await get_active_species_level(db, user["id"], "unicorn")
    if uni_lv == 0:
        raise HTTPException(400, "Нет активного Единорога в питомнике.")

    u_b = UNICORN_BONUSES.get(max(1, min(10, uni_lv)), {})
    immunity_uses = u_b.get("immunity_uses", 0)
    immunity_hours = u_b.get("immunity_hours", 0)
    if immunity_uses == 0:
        raise HTTPException(400, "Единорог должен быть Lv4+ для этой способности.")

    today_key = f"unicorn_immunity_{_dt.now().strftime('%Y-%m-%d')}"
    async with db.execute(
        "SELECT 1 FROM player_buffs WHERE user_id = ? AND buff_type = ?",
        (user["id"], today_key),
    ) as c:
        if await c.fetchone():
            raise HTTPException(400, "Иммунитет уже использован сегодня.")

    expires_str = (_dt.now() + _td(hours=immunity_hours)).strftime("%Y-%m-%d %H:%M:%S")

    await db.execute(
        "INSERT INTO player_buffs (user_id, buff_type, uses_left, expires_at) "
        "VALUES (?, ?, 1, NOW() + INTERVAL '2 days') "
        "ON CONFLICT (user_id, buff_type) DO UPDATE SET expires_at = NOW() + INTERVAL '2 days'",
        (user["id"], today_key),
    )
    await db.execute(
        "INSERT INTO player_buffs (user_id, buff_type, uses_left, expires_at) "
        "VALUES (?, 'unicorn_immunity', 1, ?) "
        "ON CONFLICT (user_id, buff_type) DO UPDATE SET expires_at = ?, uses_left = 1",
        (user["id"], expires_str, expires_str),
    )
    await db.commit()

    return {"ok": True, "immunity_hours": immunity_hours, "expires_at": expires_str}


@router.post("/collect")
async def collect_hamster(db=Depends(get_db), user=Depends(require_tg_user)):
    """Собрать накопленную Мору от Хомяков-банкиров."""
    import random
    from datetime import datetime as _dt

    await apply_fatigue_decay(db, user["id"])
    stats = await get_zoo_stats(db, user["id"])

    async with db.execute(
        "SELECT COALESCE(pet_level,1) AS pet_level, fatigue, placement FROM pets "
        "WHERE owner_id = ? AND species_id = 'hamster' AND placement IN ('active','passive')",
        (user["id"],),
    ) as c:
        hamster_rows = [dict(r) for r in await c.fetchall()]

    # Block 12: бонус хомяка с учётом слота (passive ×0.5, ignore_exhaustion off)
    productive = [
        h for h in hamster_rows
        if h["fatigue"] < 100 or hamster_bonus(h).get("ignore_exhaustion", False)
    ]

    if not productive:
        raise HTTPException(400, "В Питомнике нет бодрствующих Хомяков-банкиров.")

    accumulated = await get_pending_hamster_income(db, user["id"])
    if accumulated < 1:
        raise HTTPException(400, "Хомяки ещё не накопили Мору. Попробуйте через несколько минут.")

    double_mora_bonus = 0
    diamond_bonus = 0.0
    today_str = _dt.now().strftime("%Y-%m-%d")
    last_collect_dt = parse_dt(stats.get("last_income_collection"))
    last_collect_day = last_collect_dt.strftime("%Y-%m-%d") if last_collect_dt else ""

    for h in productive:
        b = hamster_bonus(h)
        if b.get("double_chance", 0.0) > 0 and random.random() < b["double_chance"]:
            double_mora_bonus += int(accumulated / max(1, len(productive)))
        if b.get("daily_diamond", 0.0) > 0 and last_collect_day != today_str:
            diamond_bonus = max(diamond_bonus, b["daily_diamond"])

    dragon_bonus_mora = int((await get_species_bonus(db, user["id"], "dragon")).get("hamster_collect_bonus", 0.0))

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
