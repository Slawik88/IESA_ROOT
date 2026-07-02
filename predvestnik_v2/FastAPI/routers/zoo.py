"""FastAPI/routers/zoo.py — питомцы: просмотр, кормление, экспедиции, управление."""
import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.constants import (
    get_pet_bonus, get_total_duplicates_for_level, PET_LEVEL_MILESTONE_REWARDS,
    WOLF_BONUSES, UNICORN_BONUSES,
)
from core.registry import ITEMS_REGISTRY, PET_SPECIES, EXPEDITIONS_DATA
from FastAPI.deps import get_db, require_tg_user, require_module
from infrastructure.repositories.economy import get_item_quantity, remove_item, add_balance, spend_mora, get_balance
from infrastructure.repositories.zoo import (
    get_user_pets, get_nursery_count, get_zoo_stats, buy_pet_slot, get_slot_purchase_state,
    get_active_count, get_pending_hamster_income, get_active_species_level, apply_fatigue_decay,
    get_species_bonus, hamster_bonus,
    get_pet_owned, get_active_pet, get_busy_expedition, get_active_expeditions_detailed,
    pet_has_active_expedition, create_expedition, add_pet_fatigue, set_pet_fatigue,
    end_expedition_now, apply_food_aoe, apply_pet_move, get_buff_uses_left,
    buff_used_today, get_active_buff_expiry, consume_wolf_restore, grant_unicorn_immunity,
    get_productive_hamsters, set_last_income_collection, apply_expedition_boost_time,
)
from services.formatting import parse_dt
from services.vip import get_extra_pet_slots
from services.zoo import get_active_wolf_food_extra, get_wolf_fatigue_reduction, movement_fatigue_cost

router = APIRouter(prefix="/zoo", tags=["zoo"], dependencies=[Depends(require_module("module_zoo"))])

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
        uses_left = await get_buff_uses_left(db, user["id"], f"wolf_restore_{today_key}", max_uses)
        wolf_restore_info = {"uses_left": uses_left, "max_uses": max_uses,
                             "restore_amount": w_b.get("daily_restore_amount", 30)}

    # Unicorn Lv4+ immunity ability status
    unicorn_ability_info = None
    uni_lv = await get_active_species_level(db, user["id"], "unicorn")
    if uni_lv >= 4:
        u_b = UNICORN_BONUSES.get(max(1, min(10, uni_lv)), {})
        used_today = await buff_used_today(db, user["id"], f"unicorn_immunity_{today_key}")
        expires_at = await get_active_buff_expiry(db, user["id"], "unicorn_immunity")
        unicorn_ability_info = {
            "available": not used_today,
            "immunity_hours": u_b.get("immunity_hours", 0),
            "active": expires_at is not None,
            "expires_at": str(expires_at) if expires_at else None,
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
    pet = await get_pet_owned(db, pet_id, user["id"])
    if not pet:
        raise HTTPException(404, "Питомец не найден.")
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
    rows = await get_active_expeditions_detailed(db, user["id"])

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

    pet = await get_pet_owned(db, body.pet_id, user["id"])
    if not pet:
        raise HTTPException(404, "Питомец не найден.")

    ok = await remove_item(db, user["id"], body.food_id, 1, commit=False)
    if not ok:
        raise HTTPException(400, f"Нет {item['name']} в инвентаре.")

    wolf_extra = await get_active_wolf_food_extra(db, user["id"])
    restore = item["fatigue_restore"] + wolf_extra
    new_fatigue = max(0, pet["fatigue"] - restore)
    await set_pet_fatigue(db, body.pet_id, new_fatigue)

    # food_super: −10 усталости всем остальным питомцам в питомнике (AoE)
    # food_diamond: ПОЛНЫЙ сброс усталости активному И ВСЕМ питомцам (премиум AoE)
    await apply_food_aoe(db, user["id"], body.food_id, body.pet_id)
    if body.food_id == "food_diamond":
        new_fatigue = 0
    # food_energy: мгновенно завершить текущий поход (вернуть питомца с лутом сразу).
    # Раньше веб этого НЕ делал — эффект работал только в боте (рассинхрон).
    if body.food_id == "food_energy":
        await end_expedition_now(db, body.pet_id)

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

    if not await pet_has_active_expedition(db, body.pet_id, user["id"]):
        raise HTTPException(404, "Экспедиция не найдена.")

    # Atomic: remove item + update expedition time to prevent double-boost race.
    # Инвентарный FOR UPDATE намеренно inline (не через remove_item) — он должен быть
    # частью ОДНОЙ транзакции вместе с обновлением active_expeditions ниже.
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
            await apply_expedition_boost_time(db, body.pet_id, boost_hours)
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
    active_pet = await get_active_pet(db, uid)
    busy = await get_busy_expedition(db, uid)
    balance = await get_balance(db, uid)
    return {
        "options": options,
        "active_pet": active_pet,
        "busy": busy is not None,
        "busy_until": str(busy["ends_at"])[:16] if busy else None,
        "busy_pet": busy["name"] if busy else None,
        "mora": float(balance["user_balance_mora"] or 0),
    }


class StartExpeditionRequest(BaseModel):
    hours: int
    chat_id: int = 0


@router.post("/start-expedition")
async def start_expedition(body: StartExpeditionRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Отправить активного питомца в поход. Синхронизировано с bot/handlers/expeditions.py."""
    if body.hours not in EXPEDITIONS_DATA:
        raise HTTPException(400, "Доступная длительность: 2, 4, 6 или 8 часов.")

    exp_data = EXPEDITIONS_DATA[body.hours]
    user_id = user["id"]

    pet = await get_active_pet(db, user_id)
    if not pet:
        raise HTTPException(400, "Нет активного питомца. Переведите питомца в статус Активный.")

    pet_id, pet_name, species_id, fatigue = pet["id"], pet["name"], pet["species_id"], pet["fatigue"]

    busy = await get_busy_expedition(db, user_id)
    if busy:
        raise HTTPException(400, f"Питомец уже в походе (вернётся {str(busy['ends_at'])[:16]}).")

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
            # chat_id здесь — не просто для уведомления: expedition_background_task
            # инкрементирует квест/ачивку "expeditions_today" С ЭТИМ chat_id при
            # завершении похода (квесты скоуплены per-chat). chat_id=0 раньше слал
            # прогресс в несуществующий чат — квест с веба никогда не засчитывался.
            await create_expedition(db, pet_id, body.chat_id, body.hours, actual_cost, duration_hours)
            await add_pet_fatigue(db, pet_id, expedition_fatigue)
    except Exception as e:
        if actual_cost > 0:
            await add_balance(db, user_id, mora=actual_cost)
        # Двойной тап «Отправить» — гонка между предварительной проверкой (выше) и
        # INSERT: PK(pet_id) корректно не даёт второй активной экспедиции на того
        # же питомца. Дружелюбное 400 вместо общего 500 — поведение ожидаемое.
        if "active_expeditions_pkey" in str(e) or "duplicate key" in str(e).lower():
            raise HTTPException(400, "Питомец уже в походе. Мора возвращена.")
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

    pet = await get_pet_owned(db, body.pet_id, user["id"])
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

    # Единая формула цены перемещения (скидка Волка + Lv10-иммунитет) — как в боте.
    # Цена берётся при ЛЮБОМ перемещении, включая уход на склад (бот всегда так делал
    # и показывает это в кнопках) — раньше сайт молча не брал её за склад.
    fatigue_cost = await movement_fatigue_cost(db, user["id"])
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    await apply_pet_move(db, body.pet_id, body.placement, fatigue_cost, now_str)
    await db.commit()
    return {"ok": True, "placement": body.placement, "fatigue_cost": fatigue_cost}


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
    uses_left = await get_buff_uses_left(db, user["id"], today_key, max_uses)
    if uses_left <= 0:
        raise HTTPException(400, f"Лимит восстановлений на сегодня исчерпан ({max_uses}/{max_uses}).")

    pet = await get_pet_owned(db, body.pet_id, user["id"])
    if not pet:
        raise HTTPException(404, "Питомец не найден.")
    if pet["fatigue"] == 0:
        raise HTTPException(400, "Питомец не устал.")

    new_fatigue = max(0, pet["fatigue"] - restore_amount)
    await set_pet_fatigue(db, body.pet_id, new_fatigue)
    await consume_wolf_restore(db, user["id"], today_key, max_uses - 1)
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
    if await buff_used_today(db, user["id"], today_key):
        raise HTTPException(400, "Иммунитет уже использован сегодня.")

    expires_str = (_dt.now() + _td(hours=immunity_hours)).strftime("%Y-%m-%d %H:%M:%S")
    await grant_unicorn_immunity(db, user["id"], today_key, expires_str)
    await db.commit()

    return {"ok": True, "immunity_hours": immunity_hours, "expires_at": expires_str}


@router.post("/collect")
async def collect_hamster(db=Depends(get_db), user=Depends(require_tg_user)):
    """Собрать накопленную Мору от Хомяков-банкиров."""
    import random
    from datetime import datetime as _dt

    await apply_fatigue_decay(db, user["id"])
    stats = await get_zoo_stats(db, user["id"])

    hamster_rows = await get_productive_hamsters(db, user["id"])

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
    await set_last_income_collection(db, user["id"], now_str)
    await db.commit()

    return {
        "ok": True,
        "mora": total_mora,
        "diamonds": diamond_bonus,
        "double_bonus": double_mora_bonus,
        "dragon_bonus": dragon_bonus_mora,
    }
