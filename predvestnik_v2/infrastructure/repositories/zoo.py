import aiosqlite
import random
from datetime import datetime, timedelta
from services.formatting import parse_dt

from core.registry import PET_SPECIES
from core.constants import (
    PET_ACTIVE_FATIGUE_PER_DAY, PET_PASSIVE_FATIGUE_PER_DAY, PET_MAX_FATIGUE_LAG_DAYS,
    WOLF_BONUSES, WOLF_REDUCTION_CAP,
    UNICORN_BONUSES, UNICORN_REDUCTION_CAP,
    HAMSTER_BONUSES,
    MAX_PET_COPIES,
    DUPLICATE_OVERFLOW_MORA, DUPLICATE_OVERFLOW_STARDUST,
    PET_LEVEL_MILESTONE_REWARDS,
    ZOO_BASE_SLOTS, ZOO_SLOT_PRICES_DIAMONDS,
    get_level_for_duplicates, scale_pet_bonus,
)
from infrastructure.repositories.wallet_log import log_wallet


async def init_user_zoo(db: aiosqlite.Connection, user_id: int):
    await db.execute(
        "INSERT OR IGNORE INTO user_zoo_stats (user_id, max_slots) VALUES (?, ?)",
        (user_id, 3)
    )
    await db.commit()


async def get_user_pets(db: aiosqlite.Connection, user_id: int, placement: str = None):
    query = "SELECT * FROM pets WHERE owner_id = ?"
    params = [user_id]
    if placement == "nursery":
        query += " AND placement IN ('active', 'passive')"
    elif placement:
        query += " AND placement = ?"
        params.append(placement)
    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_pet_by_id(db: aiosqlite.Connection, pet_id: int):
    async with db.execute("SELECT * FROM pets WHERE id = ?", (pet_id,)) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_zoo_stats(db: aiosqlite.Connection, user_id: int):
    await db.execute(
        "INSERT OR IGNORE INTO user_zoo_stats (user_id, max_slots) VALUES (?, 3)",
        (user_id,)
    )
    await db.commit()
    async with db.execute("SELECT * FROM user_zoo_stats WHERE user_id = ?", (user_id,)) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else {"user_id": user_id, "max_slots": 3}


def get_slot_purchase_state(max_slots: int) -> dict:
    """Состояние докупки слотов из текущего max_slots (без БД) — для отображения цены/кнопки."""
    bought = max(0, max_slots - ZOO_BASE_SLOTS)
    at_cap = bought >= len(ZOO_SLOT_PRICES_DIAMONDS)
    return {
        "base_slots": ZOO_BASE_SLOTS,
        "bought_slots": bought,
        "max_purchasable": len(ZOO_SLOT_PRICES_DIAMONDS),
        "at_cap": at_cap,
        "next_price": None if at_cap else ZOO_SLOT_PRICES_DIAMONDS[bought],
    }


async def buy_pet_slot(db, user_id: int) -> tuple[bool, str, int, int]:
    """Купить следующий слот питомника за алмазы по прогрессивной цене.
    Атомарно: блокирует user_zoo_stats и users в одной транзакции (защита от
    параллельной двойной покупки). Returns (ok, message, new_max_slots, price_paid)."""
    await db.execute(
        "INSERT INTO user_zoo_stats (user_id, max_slots) VALUES (?, ?) "
        "ON CONFLICT (user_id) DO NOTHING",
        (user_id, ZOO_BASE_SLOTS),
    )
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT max_slots FROM user_zoo_stats WHERE user_id = ? FOR UPDATE",
                (user_id,),
            ) as c:
                row = await c.fetchone()
            current = row[0] if row else ZOO_BASE_SLOTS
            bought = max(0, current - ZOO_BASE_SLOTS)
            if bought >= len(ZOO_SLOT_PRICES_DIAMONDS):
                return False, "🔒 Куплено максимум слотов за алмазы.", current, 0
            price = ZOO_SLOT_PRICES_DIAMONDS[bought]

            async with db.execute(
                "SELECT user_balance_diamonds FROM users WHERE user_tg_id = ? FOR UPDATE",
                (user_id,),
            ) as c:
                drow = await c.fetchone()
            if not drow or drow[0] < price:
                return False, f"Недостаточно Алмазов. Нужно {price} 💎.", current, price

            await db.execute(
                "UPDATE users SET user_balance_diamonds = user_balance_diamonds - ? "
                "WHERE user_tg_id = ?",
                (price, user_id),
            )
            await db.execute(
                "UPDATE user_zoo_stats SET max_slots = max_slots + 1 WHERE user_id = ?",
                (user_id,),
            )
            await log_wallet(db, user_id, delta_diamonds=-price,
                             source="zoo_slot_purchase", note=f"slot_{bought + 1}")
            new_max = current + 1
        return True, f"✅ Слот #{bought + 1} куплен за {price} 💎!", new_max, price
    except Exception as e:
        return False, f"Ошибка покупки слота: {e}", 0, 0


async def get_nursery_count(db: aiosqlite.Connection, user_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM pets WHERE owner_id = ? AND placement IN ('active', 'passive')",
        (user_id,)
    ) as c:
        return (await c.fetchone())[0]


async def get_active_count(db: aiosqlite.Connection, user_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM pets WHERE owner_id = ? AND placement = 'active'",
        (user_id,)
    ) as c:
        return (await c.fetchone())[0]


async def get_species_in_nursery_count(db: aiosqlite.Connection, user_id: int, species_id: str) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM pets WHERE owner_id = ? AND placement IN ('active', 'passive') AND species_id = ?",
        (user_id, species_id)
    ) as c:
        return (await c.fetchone())[0]


async def has_active_species(db: aiosqlite.Connection, user_id: int, species_id: str) -> bool:
    """True if user has a non-exhausted pet of this species in nursery (active or passive)."""
    async with db.execute(
        "SELECT 1 FROM pets WHERE owner_id = ? AND species_id = ? "
        "AND placement IN ('active', 'passive') AND fatigue < 100 LIMIT 1",
        (user_id, species_id)
    ) as cursor:
        return await cursor.fetchone() is not None


async def get_active_species_level(db: aiosqlite.Connection, user_id: int, species_id: str) -> int:
    """Returns level (1-10) if a non-exhausted nursery pet of this species exists, else 0."""
    async with db.execute(
        "SELECT COALESCE(pet_level, 1) FROM pets WHERE owner_id = ? AND species_id = ? "
        "AND placement IN ('active', 'passive') AND fatigue < 100 LIMIT 1",
        (user_id, species_id)
    ) as cursor:
        row = await cursor.fetchone()
    return row[0] if row else 0


async def get_species_level_placement(db, user_id: int, species_id: str) -> tuple[int, str | None]:
    """Уровень + слот непустого питомца этого вида (приоритет ACTIVE над passive).
    (0, None) если нет. Block 12: нужен для масштабирования бонуса по слоту."""
    async with db.execute(
        "SELECT COALESCE(pet_level, 1), placement FROM pets WHERE owner_id = ? AND species_id = ? "
        "AND placement IN ('active', 'passive') AND fatigue < 100 "
        "ORDER BY (placement = 'active') DESC LIMIT 1",
        (user_id, species_id),
    ) as cursor:
        row = await cursor.fetchone()
    return (row[0], row[1]) if row else (0, None)


async def get_species_bonus(db, user_id: int, species_id: str) -> dict:
    """Готовый бонус вида с учётом слота (active=полный, passive=×0.5, capstone off).
    {} если активного/пассивного питомца этого вида нет. Block 12."""
    from core.constants import get_pet_bonus, scale_pet_bonus
    level, placement = await get_species_level_placement(db, user_id, species_id)
    if level <= 0:
        return {}
    return scale_pet_bonus(get_pet_bonus(species_id, level), placement)


def hamster_bonus(pet: dict) -> dict:
    """Бонус хомяка с учётом его слота (Block 12): active — полный, passive — ×0.5,
    ignore_exhaustion в passive отключён. `pet` — dict с pet_level и placement."""
    lvl = max(1, min(10, pet.get("pet_level") or 1))
    return scale_pet_bonus(HAMSTER_BONUSES.get(lvl, {}), pet.get("placement"))


async def _list_species_pets_for_owner(db, user_id: int, species_id: str) -> list[dict]:
    """All pets of this species owned by user, sorted by copy_index ASC."""
    async with db.execute(
        "SELECT * FROM pets WHERE owner_id = ? AND species_id = ? "
        "ORDER BY COALESCE(copy_index, 1) ASC",
        (user_id, species_id),
    ) as c:
        rows = await c.fetchall()
    return [dict(r) for r in rows]


async def get_pet_milestones_received(db, pet_id: int) -> set[int]:
    async with db.execute(
        "SELECT milestone FROM pet_milestones_received WHERE pet_id = ?", (pet_id,)
    ) as c:
        return {row[0] for row in await c.fetchall()}


async def record_pet_milestone(db, pet_id: int, milestone: int) -> None:
    """Mark milestone as granted for this pet. No commit."""
    await db.execute(
        "INSERT OR IGNORE INTO pet_milestones_received (pet_id, milestone) VALUES (?, ?)",
        (pet_id, milestone),
    )


async def grant_duplicate(db, user_id: int, species_id: str) -> dict:
    """Process one duplicate of `species_id` for `user_id`.

    Logic:
    1) Look up the species rarity from PET_SPECIES.
    2) Fetch existing pets of this species (sorted by copy_index).
    3) If none exist → create copy #1 at Lv1 with this duplicate as the first one
       (duplicates_collected = 1).
    4) Else find first non-Lv10 copy → +1 duplicates_collected, recompute level.
       Collect newly crossed milestones (3, 5, 7, 10).
    5) If all existing copies are at Lv10 and count < MAX_PET_COPIES →
       create the next copy with duplicates_collected = 1.
    6) If all MAX_PET_COPIES copies are at Lv10 →
       return overflow reward (mora + stardust), no DB writes to pets.

    Does NOT commit. Caller is responsible for the transaction.

    Returns dict with:
        outcome: "first_copy_created" | "added" | "leveled_up" |
                 "new_copy_created" | "overflow"
        pet_id: int | None
        copy_index: int
        new_level: int
        prev_level: int
        new_duplicates: int
        milestones_unlocked: list[int]
        rarity: str
        overflow: {"mora": float, "stardust": int} | None
    """
    species_data = PET_SPECIES.get(species_id, {})
    rarity = species_data.get("rarity", "common")
    pet_name = species_data.get("name", species_id)

    pets = await _list_species_pets_for_owner(db, user_id, species_id)

    # Case 1: no existing pet of this species
    if not pets:
        async with db.execute(
            "INSERT INTO pets "
            "(owner_id, species_id, rarity, name, placement, fatigue, is_summoned, "
            "pet_level, duplicates_collected, copy_index) "
            "VALUES (?, ?, ?, ?, 'storage', 0, FALSE, 1, 1, 1) RETURNING id",
            (user_id, species_id, rarity, pet_name),
        ) as _c:
            _r = await _c.fetchone()
        new_pet_id = _r[0] if _r else 0
        return {
            "outcome": "first_copy_created",
            "pet_id": new_pet_id,
            "copy_index": 1,
            "new_level": 1,
            "prev_level": 0,
            "new_duplicates": 1,
            "milestones_unlocked": [],
            "rarity": rarity,
            "overflow": None,
        }

    # Case 2: find first non-Lv10 copy
    target = next((p for p in pets if (p.get("pet_level") or 1) < 10), None)

    if target is not None:
        prev_level = target.get("pet_level") or 1
        new_dups = (target.get("duplicates_collected") or 0) + 1
        new_level = get_level_for_duplicates(rarity, new_dups)
        await db.execute(
            "UPDATE pets SET duplicates_collected = ?, pet_level = ? WHERE id = ?",
            (new_dups, new_level, target["id"]),
        )
        milestones_unlocked = [
            m for m in PET_LEVEL_MILESTONE_REWARDS.keys()
            if prev_level < m <= new_level
        ]
        return {
            "outcome": "leveled_up" if new_level > prev_level else "added",
            "pet_id": target["id"],
            "copy_index": target.get("copy_index") or 1,
            "new_level": new_level,
            "prev_level": prev_level,
            "new_duplicates": new_dups,
            "milestones_unlocked": milestones_unlocked,
            "rarity": rarity,
            "overflow": None,
        }

    # Case 3: all existing copies at Lv10, capacity available → create new copy
    if len(pets) < MAX_PET_COPIES:
        next_index = max((p.get("copy_index") or 1) for p in pets) + 1
        async with db.execute(
            "INSERT INTO pets "
            "(owner_id, species_id, rarity, name, placement, fatigue, is_summoned, "
            "pet_level, duplicates_collected, copy_index) "
            "VALUES (?, ?, ?, ?, 'storage', 0, FALSE, 1, 1, ?) RETURNING id",
            (user_id, species_id, rarity, pet_name, next_index),
        ) as _c:
            _r = await _c.fetchone()
        return {
            "outcome": "new_copy_created",
            "pet_id": _r[0] if _r else 0,
            "copy_index": next_index,
            "new_level": 1,
            "prev_level": 0,
            "new_duplicates": 1,
            "milestones_unlocked": [],
            "rarity": rarity,
            "overflow": None,
        }

    # Case 4: all MAX_PET_COPIES are at Lv10 → overflow compensation
    return {
        "outcome": "overflow",
        "pet_id": None,
        "copy_index": MAX_PET_COPIES,
        "new_level": 10,
        "prev_level": 10,
        "new_duplicates": 0,
        "milestones_unlocked": [],
        "rarity": rarity,
        "overflow": {
            "mora": DUPLICATE_OVERFLOW_MORA.get(rarity, 0.0),
            "stardust": DUPLICATE_OVERFLOW_STARDUST.get(rarity, 0),
        },
    }


async def apply_fatigue_decay(db: aiosqlite.Connection, user_id: int):
    """Lazily apply accumulated daily fatigue to all of the user's nursery pets."""
    now = datetime.now()

    # Wolf reduction
    wolf_reduction = 0.0
    async with db.execute(
        "SELECT placement, COALESCE(pet_level, 1) FROM pets WHERE owner_id = ? "
        "AND species_id = 'wolf' AND placement IN ('active', 'passive') AND fatigue < 100 LIMIT 1",
        (user_id,)
    ) as c:
        row = await c.fetchone()
        if row:
            wolf_bonus = WOLF_BONUSES.get(max(1, min(10, row[1])), {})
            wolf_reduction = min(
                wolf_bonus.get("active_reduction" if row[0] == "active" else "passive_reduction", 0.0),
                WOLF_REDUCTION_CAP,
            )

    # Unicorn: reduction + Lv8 active recovery + Lv10 auto-recover
    unicorn_reduction = 0.0
    unicorn_auto_recover = False
    unicorn_active_recovery_ph = 0  # fatigue/hour healed for unicorn itself if in active slot
    unicorn_active_pet_id = None
    async with db.execute(
        "SELECT id, placement, COALESCE(pet_level, 1) FROM pets WHERE owner_id = ? "
        "AND species_id = 'unicorn' AND placement IN ('active', 'passive') AND fatigue < 100 LIMIT 1",
        (user_id,)
    ) as c:
        row = await c.fetchone()
        if row:
            uni_lv = max(1, min(10, row[2]))
            # Block 12: в passive — числовые ×0.5, auto_recover off (active → без изменений)
            uni_bonus = scale_pet_bonus(UNICORN_BONUSES.get(uni_lv, {}), row[1])
            unicorn_reduction = min(uni_bonus.get("daily_fatigue_reduction", 0.0), UNICORN_REDUCTION_CAP)
            unicorn_auto_recover = uni_bonus.get("auto_recover", False)
            if row[1] == "active":
                unicorn_active_recovery_ph = uni_bonus.get("active_recovery_per_hour", 0)
                unicorn_active_pet_id = row[0]

    # Unicorn Lv4+ immunity: check player_buffs
    unicorn_immune = False
    async with db.execute(
        "SELECT 1 FROM player_buffs WHERE user_id = ? AND buff_type = 'unicorn_immunity' "
        "AND expires_at > NOW() LIMIT 1",
        (user_id,)
    ) as c:
        if await c.fetchone():
            unicorn_immune = True

    # Fetch all nursery pets
    async with db.execute(
        "SELECT id, placement, fatigue, last_fatigue_update "
        "FROM pets WHERE owner_id = ? AND placement IN ('active', 'passive')",
        (user_id,)
    ) as c:
        pets = [dict(r) for r in await c.fetchall()]

    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    for pet in pets:
        last_upd = pet.get("last_fatigue_update")
        if not last_upd:
            await db.execute("UPDATE pets SET last_fatigue_update = ? WHERE id = ?", (now_str, pet["id"]))
            continue

        try:
            last_dt = parse_dt(last_upd)
        except ValueError:
            await db.execute("UPDATE pets SET last_fatigue_update = ? WHERE id = ?", (now_str, pet["id"]))
            continue

        max_lag = timedelta(days=PET_MAX_FATIGUE_LAG_DAYS)
        if now - last_dt > max_lag:
            last_dt = now - max_lag

        elapsed_seconds = (now - last_dt).total_seconds()

        # Unicorn Lv8+ in active slot: the unicorn itself HEALS instead of gaining fatigue
        if pet["id"] == unicorn_active_pet_id and unicorn_active_recovery_ph > 0:
            heal_per_second = unicorn_active_recovery_ph / 3600.0
            heal_int = int(elapsed_seconds * heal_per_second)
            if heal_int > 0 and pet["fatigue"] > 0:
                new_fatigue = max(0, pet["fatigue"] - heal_int)
                consumed = heal_int / heal_per_second
                new_last_dt = last_dt + timedelta(seconds=consumed)
                await db.execute(
                    "UPDATE pets SET fatigue = ?, last_fatigue_update = ? WHERE id = ?",
                    (new_fatigue, new_last_dt.strftime("%Y-%m-%d %H:%M:%S"), pet["id"])
                )
            else:
                await db.execute("UPDATE pets SET last_fatigue_update = ? WHERE id = ?", (now_str, pet["id"]))
            continue

        # Unicorn immunity active: skip fatigue gain, just advance timestamp
        if unicorn_immune:
            await db.execute("UPDATE pets SET last_fatigue_update = ? WHERE id = ?", (now_str, pet["id"]))
            continue

        base_rate = (
            PET_ACTIVE_FATIGUE_PER_DAY if pet["placement"] == "active"
            else PET_PASSIVE_FATIGUE_PER_DAY
        )
        effective_rate = base_rate * (1.0 - wolf_reduction)
        if unicorn_reduction > 0:
            effective_rate *= (1.0 - unicorn_reduction)

        if effective_rate <= 0:
            continue

        seconds_per_point = 86400.0 / effective_rate
        gain_int = int(elapsed_seconds / seconds_per_point)

        if gain_int > 0:
            new_fatigue = min(100, pet["fatigue"] + gain_int)
            # Unicorn Lv10: auto-recover when pet would hit 100 fatigue
            if unicorn_auto_recover and new_fatigue >= 100:
                new_fatigue = max(0, new_fatigue - 30)
            consumed_seconds = gain_int * seconds_per_point
            new_last_dt = last_dt + timedelta(seconds=consumed_seconds)
            await db.execute(
                "UPDATE pets SET fatigue = ?, last_fatigue_update = ? WHERE id = ?",
                (new_fatigue, new_last_dt.strftime("%Y-%m-%d %H:%M:%S"), pet["id"])
            )

    await db.commit()


async def get_pending_hamster_income(db: aiosqlite.Connection, user_id: int) -> float:
    """Return accumulated mora from all non-exhausted nursery hamsters (not yet collected).
    Each hamster's income rate and cap come from its level (HAMSTER_BONUSES).
    A Lv4+ hamster keeps accumulating even at fatigue == 100."""
    async with db.execute(
        "SELECT last_income_collection FROM user_zoo_stats WHERE user_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()

    if not row or not row[0]:
        # Never collected — treat as if last collection was 24h ago so income is visible.
        # Also initialize the timestamp so subsequent calls have a reference point.
        fallback = datetime.now() - timedelta(hours=24)
        await db.execute(
            "INSERT INTO user_zoo_stats (user_id, max_slots, last_income_collection) VALUES (?, 3, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET last_income_collection = COALESCE(user_zoo_stats.last_income_collection, EXCLUDED.last_income_collection)",
            (user_id, fallback.strftime("%Y-%m-%d %H:%M:%S")),
        )
        last_dt = fallback
    else:
        try:
            last_dt = parse_dt(row[0])
        except ValueError:
            return 0.0

    hours = (datetime.now() - last_dt).total_seconds() / 3600.0

    # Pull every hamster the user has in the nursery. Lv4+ also keeps earning at fatigue 100.
    # Block 12: бонус масштабируется по слоту (passive — вдвое слабее).
    async with db.execute(
        "SELECT COALESCE(pet_level, 1), fatigue, placement FROM pets WHERE owner_id = ? "
        "AND species_id = 'hamster' AND placement IN ('active', 'passive')",
        (user_id,),
    ) as c:
        hamsters = await c.fetchall()

    total = 0.0
    for level, fatigue, placement in hamsters:
        bonus = hamster_bonus({"pet_level": level, "placement": placement})
        if fatigue >= 100 and not bonus.get("ignore_exhaustion", False):
            continue
        rate = bonus.get("mora_per_hour", 0.0)
        cap = bonus.get("cap", 0)
        total += min(hours * rate, float(cap))

    return round(total, 2)


# open_egg / open_eggs_batch УДАЛЕНЫ (БЛОК19 Ч.2): яйца вырезаны, питомцы добываются
# ТОЛЬКО через Гачу (services/gacha.py → grant_duplicate). Удача lucky_charm переехала
# в гача-крутку (_consume_luck_potions); turtle double_egg_chance ретайрнут.


# ── Пилот CODE_STRUCTURE_AUDIT.md: SQL из FastAPI/routers/zoo.py, вынесенный сюда ──────

async def get_pet_owned(db, pet_id: int, owner_id: int) -> dict | None:
    """Питомец по id, только если принадлежит owner_id (иначе None)."""
    async with db.execute(
        "SELECT * FROM pets WHERE id = ? AND owner_id = ?",
        (pet_id, owner_id),
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def get_active_pet(db, owner_id: int) -> dict | None:
    """Единственный активный питомец игрока (или None). Полный набор колонок —
    вызывающий код берёт только нужные (expedition_options использует rarity/pet_level,
    start_expedition — только species_id/fatigue)."""
    async with db.execute(
        "SELECT id, name, species_id, rarity, COALESCE(pet_level,1) AS pet_level, fatigue "
        "FROM pets WHERE owner_id = ? AND placement = 'active' ORDER BY id LIMIT 1",
        (owner_id,),
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def get_busy_expedition(db, owner_id: int) -> dict | None:
    """Активная (незавершённая) экспедиция игрока — {ends_at, name} или None."""
    async with db.execute(
        "SELECT ae.ends_at, p.name FROM active_expeditions ae JOIN pets p ON ae.pet_id = p.id "
        "WHERE p.owner_id = ? AND ae.ends_at > NOW() ORDER BY ae.ends_at DESC LIMIT 1",
        (owner_id,),
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def get_active_expeditions_detailed(db, owner_id: int) -> list[dict]:
    """Все активные экспедиции игрока с именем/видом питомца (для UI списка)."""
    async with db.execute(
        "SELECT e.pet_id, e.duration_hours, e.ends_at, p.name, p.species_id "
        "FROM active_expeditions e JOIN pets p ON e.pet_id = p.id "
        "WHERE p.owner_id = ?",
        (owner_id,),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def pet_has_active_expedition(db, pet_id: int, owner_id: int) -> bool:
    async with db.execute(
        "SELECT e.pet_id FROM active_expeditions e "
        "JOIN pets p ON e.pet_id = p.id "
        "WHERE e.pet_id = ? AND p.owner_id = ?",
        (pet_id, owner_id),
    ) as c:
        return await c.fetchone() is not None


async def create_expedition(db, pet_id: int, chat_id: int, hours: int,
                             cost_mora: float, duration_hours: float) -> None:
    await db.execute(
        "INSERT INTO active_expeditions (pet_id, chat_id, duration_hours, cost_mora, ends_at) "
        "VALUES (?, ?, ?, ?, NOW() + (? * INTERVAL '1 hour'))",
        (pet_id, chat_id, hours, cost_mora, duration_hours),
    )


async def add_pet_fatigue(db, pet_id: int, delta: int) -> None:
    await db.execute("UPDATE pets SET fatigue = fatigue + ? WHERE id = ?", (delta, pet_id))


async def set_pet_fatigue(db, pet_id: int, value: int) -> None:
    await db.execute("UPDATE pets SET fatigue = ? WHERE id = ?", (value, pet_id))


async def end_expedition_now(db, pet_id: int) -> None:
    """food_energy: мгновенно завершить текущий поход питомца."""
    await db.execute(
        "UPDATE active_expeditions SET ends_at = CURRENT_TIMESTAMP WHERE pet_id = ?",
        (pet_id,),
    )


async def apply_food_aoe(db, owner_id: int, food_id: str, exclude_pet_id: int) -> None:
    """AoE-эффекты премиум-корма на весь питомник (кроме уже обработанного питомца)."""
    if food_id == "food_super":
        await db.execute(
            "UPDATE pets SET fatigue = GREATEST(0, fatigue - 10) "
            "WHERE owner_id = ? AND placement IN ('active', 'passive') AND id != ?",
            (owner_id, exclude_pet_id),
        )
    elif food_id == "food_diamond":
        await db.execute("UPDATE pets SET fatigue = 0 WHERE owner_id = ?", (owner_id,))


async def set_pet_placement(db, pet_id: int, placement: str, *,
                             restore_fatigue: int = 0, now_str: str | None = None) -> None:
    """Переместить питомца в новый слот. Если `now_str` задан — это вход в питомник
    (active/passive): обновляем last_fatigue_update, опционально доначисляем
    `restore_fatigue` (0 при Волк Lv10 movement_immunity). Иначе — уход в storage,
    без изменения усталости."""
    if now_str is not None:
        if restore_fatigue:
            await db.execute(
                "UPDATE pets SET placement = ?, "
                "fatigue = LEAST(100, fatigue + ?), "
                "last_fatigue_update = ? WHERE id = ?",
                (placement, restore_fatigue, now_str, pet_id),
            )
        else:
            await db.execute(
                "UPDATE pets SET placement = ?, last_fatigue_update = ? WHERE id = ?",
                (placement, now_str, pet_id),
            )
    else:
        await db.execute("UPDATE pets SET placement = ? WHERE id = ?", (placement, pet_id))


async def get_buff_uses_left(db, user_id: int, buff_type: str, default: int) -> int:
    async with db.execute(
        "SELECT uses_left FROM player_buffs WHERE user_id = ? AND buff_type = ?",
        (user_id, buff_type),
    ) as c:
        row = await c.fetchone()
    return row["uses_left"] if row else default


async def buff_used_today(db, user_id: int, buff_type: str) -> bool:
    async with db.execute(
        "SELECT 1 FROM player_buffs WHERE user_id = ? AND buff_type = ?",
        (user_id, buff_type),
    ) as c:
        return await c.fetchone() is not None


async def get_active_buff_expiry(db, user_id: int, buff_type: str):
    """expires_at активного (ещё не истёкшего) баффа этого типа, или None."""
    async with db.execute(
        "SELECT expires_at FROM player_buffs WHERE user_id = ? "
        "AND buff_type = ? AND expires_at > NOW()",
        (user_id, buff_type),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else None


async def consume_wolf_restore(db, user_id: int, today_key: str, uses_left_after: int) -> None:
    await db.execute(
        "INSERT INTO player_buffs (user_id, buff_type, uses_left, expires_at) "
        "VALUES (?, ?, ?, NOW() + INTERVAL '2 days') "
        "ON CONFLICT (user_id, buff_type) DO UPDATE SET uses_left = player_buffs.uses_left - 1",
        (user_id, today_key, uses_left_after),
    )


async def grant_unicorn_immunity(db, user_id: int, today_key: str, expires_str: str) -> None:
    """Отмечает суточный лимит (today_key) + выставляет реальный баф 'unicorn_immunity'."""
    await db.execute(
        "INSERT INTO player_buffs (user_id, buff_type, uses_left, expires_at) "
        "VALUES (?, ?, 1, NOW() + INTERVAL '2 days') "
        "ON CONFLICT (user_id, buff_type) DO UPDATE SET expires_at = NOW() + INTERVAL '2 days'",
        (user_id, today_key),
    )
    await db.execute(
        "INSERT INTO player_buffs (user_id, buff_type, uses_left, expires_at) "
        "VALUES (?, 'unicorn_immunity', 1, ?) "
        "ON CONFLICT (user_id, buff_type) DO UPDATE SET expires_at = ?, uses_left = 1",
        (user_id, expires_str, expires_str),
    )


async def get_productive_hamsters(db, owner_id: int) -> list[dict]:
    """Хомяки-банкиры в питомнике (active/passive) — сырые строки для расчёта бонусов."""
    async with db.execute(
        "SELECT COALESCE(pet_level,1) AS pet_level, fatigue, placement FROM pets "
        "WHERE owner_id = ? AND species_id = 'hamster' AND placement IN ('active','passive')",
        (owner_id,),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def set_last_income_collection(db, user_id: int, now_str: str) -> None:
    await db.execute(
        "UPDATE user_zoo_stats SET last_income_collection = ? WHERE user_id = ?",
        (now_str, user_id),
    )


async def apply_expedition_boost_time(db, pet_id: int, boost_hours: float) -> None:
    """Сократить время похода на boost_hours (не раньше чем через 30с от сейчас)."""
    await db.execute(
        f"UPDATE active_expeditions "
        f"SET ends_at = GREATEST(NOW() + INTERVAL '30 seconds', ends_at - ({boost_hours} * INTERVAL '1 hour')) "
        f"WHERE pet_id = ?",
        (pet_id,),
    )


async def apply_pet_move(db, pet_id: int, placement: str, fatigue_cost: int, now_str: str) -> None:
    """Перемещение питомца — ВЕРСИЯ БОТА (bot/handlers/zoo.py).

    ВНИМАНИЕ — расхождение с сайтом (CODE_STRUCTURE_AUDIT.md, найдено при выносе SQL
    2026-07-02, НЕ унифицировано, решение за пользователем): бот начисляет
    fatigue_cost (уменьшенный бонусом Волка через get_wolf_fatigue_reduction, любая
    непрерывная скидка) ПРИ ЛЮБОМ перемещении, включая уход на склад. Сайт
    (services/zoo.set_pet_placement) начисляет фиксированный PET_PLACEMENT_FATIGUE_RESTORE
    только при входе в питомник, ноль при уходе на склад, и даёт Волку Lv10 полный
    иммунитет (0 усталости) вместо непрерывной скидки. Сохранено «как было» при
    рефакторинге — это НЕ исправление поведения, а перенос SQL как есть."""
    if placement != "storage":
        await db.execute(
            "UPDATE pets SET placement = ?, fatigue = LEAST(100, fatigue + ?), "
            "last_fatigue_update = ? WHERE id = ?",
            (placement, fatigue_cost, now_str, pet_id),
        )
    else:
        await db.execute(
            "UPDATE pets SET placement = ?, fatigue = LEAST(100, fatigue + ?) WHERE id = ?",
            (placement, fatigue_cost, pet_id),
        )


async def delete_pet(db, pet_id: int) -> None:
    await db.execute("DELETE FROM pets WHERE id = ?", (pet_id,))
