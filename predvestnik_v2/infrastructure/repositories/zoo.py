import aiosqlite
import random
from datetime import datetime, timedelta
from services.formatting import parse_dt

from core.registry import GACHA_RATES, PET_SPECIES
from core.constants import (
    PET_ACTIVE_FATIGUE_PER_DAY, PET_PASSIVE_FATIGUE_PER_DAY, PET_MAX_FATIGUE_LAG_DAYS,
    WOLF_BONUSES, WOLF_REDUCTION_CAP,
    UNICORN_BONUSES, UNICORN_REDUCTION_CAP,
    FOX_BONUSES, TURTLE_BONUSES,
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


async def open_egg(db: aiosqlite.Connection, user_id: int, egg_id: str, is_summoned: bool = False):
    results = await open_eggs_batch(db, user_id, egg_id, 1, is_summoned=is_summoned)
    return (True, results[0]) if results else (False, "Ошибка при открытии")


async def open_eggs_batch(
    db: aiosqlite.Connection, user_id: int, egg_id: str, count: int, is_summoned: bool = False
) -> list[dict]:
    """Open `count` eggs. Each roll goes through grant_duplicate so that:
      - first time getting a species → creates copy #1 at Lv1
      - subsequent times → adds duplicate to first non-Lv10 copy (auto level-up)
      - after all MAX_PET_COPIES at Lv10 → overflow compensation

    `is_summoned` is forwarded as a hint on the FIRST creation of any new copy.
    Returns a list of result dicts (see grant_duplicate signature) enriched with
    species_name and species_id for the caller.
    """
    rates = GACHA_RATES.get(egg_id)
    if not rates:
        return []
    results: list[dict] = []
    try:
        await db.execute("BEGIN IMMEDIATE")

        # Lock inventory row with FOR UPDATE before processing to prevent
        # concurrent requests from both opening the same eggs (negative inventory)
        async with db.execute(
            "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ? FOR UPDATE",
            (user_id, egg_id),
        ) as _c:
            _inv_row = await _c.fetchone()
        if not _inv_row or _inv_row[0] < count:
            await db.rollback()
            return []

        # Check lucky_charm: +15% rarity boost on first egg of the batch
        lucky_charm_active = False
        async with db.execute(
            "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = 'lucky_charm' AND quantity > 0",
            (user_id,),
        ) as _lc:
            _lc_row = await _lc.fetchone()
        if _lc_row:
            lucky_charm_active = True
            await db.execute(
                "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = 'lucky_charm'",
                (user_id,),
            )

        # Fox Lv4+: common_dup_bonus — chance to reroll non-common result to common
        fox_level = await get_active_species_level(db, user_id, "fox")
        fox_common_bonus = (
            FOX_BONUSES.get(max(1, min(10, fox_level)), {}).get("common_dup_bonus", 0.0)
            if fox_level >= 4 else 0.0
        )

        # Turtle Lv10: double_egg_chance — 5% chance for a bonus free pet per egg
        turtle_level = await get_active_species_level(db, user_id, "turtle")
        double_egg_chance = (
            TURTLE_BONUSES.get(max(1, min(10, turtle_level)), {}).get("double_egg_chance", 0.0)
            if turtle_level > 0 else 0.0
        )

        def _roll_one(boost_rand: bool = False) -> str:
            rand = random.randint(1, 100)
            if boost_rand:
                rand = max(1, rand - 15)
            cumulative = 0
            selected = "common"
            for rarity, chance in rates.items():
                cumulative += chance
                if rand <= cumulative:
                    selected = rarity
                    break
            # Fox: reroll non-common to common
            if fox_common_bonus > 0 and selected != "common" and random.random() < fox_common_bonus:
                selected = "common"
            return random.choice([s for s, d in PET_SPECIES.items() if d["rarity"] == selected])

        for i in range(count):
            species_id = _roll_one(boost_rand=(lucky_charm_active and i == 0))
            result = await grant_duplicate(db, user_id, species_id)
            if is_summoned and result["outcome"] in ("first_copy_created", "new_copy_created"):
                await db.execute("UPDATE pets SET is_summoned = TRUE WHERE id = ?", (result["pet_id"],))
            result["species_id"] = species_id
            result["species_name"] = PET_SPECIES[species_id]["name"]
            results.append(result)

            # Turtle Lv10: bonus free pet from same egg
            if double_egg_chance > 0 and random.random() < double_egg_chance:
                bonus_species = _roll_one()
                bonus_result = await grant_duplicate(db, user_id, bonus_species)
                bonus_result["species_id"] = bonus_species
                bonus_result["species_name"] = PET_SPECIES[bonus_species]["name"]
                bonus_result["bonus_egg"] = True
                results.append(bonus_result)

        await db.execute(
            "UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND item_id = ?",
            (count, user_id, egg_id)
        )
        await db.commit()
        return results
    except Exception:
        await db.rollback()
        raise
