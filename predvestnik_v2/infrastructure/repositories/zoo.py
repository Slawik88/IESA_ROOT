import aiosqlite
import random
from datetime import datetime, timedelta

from core.registry import GACHA_RATES, PET_SPECIES
from core.constants import (
    PET_ACTIVE_FATIGUE_PER_DAY, PET_PASSIVE_FATIGUE_PER_DAY, PET_MAX_FATIGUE_LAG_DAYS,
    WOLF_BONUSES, WOLF_REDUCTION_CAP,
    UNICORN_BONUSES, UNICORN_REDUCTION_CAP,
    HAMSTER_BONUSES,
    MAX_PET_COPIES,
    DUPLICATE_OVERFLOW_MORA, DUPLICATE_OVERFLOW_STARDUST,
    PET_LEVEL_MILESTONE_REWARDS,
    get_level_for_duplicates,
)


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
        cursor = await db.execute(
            "INSERT INTO pets "
            "(owner_id, species_id, rarity, name, placement, fatigue, is_summoned, "
            "pet_level, duplicates_collected, copy_index) "
            "VALUES (?, ?, ?, ?, 'storage', 0, 0, 1, 1, 1)",
            (user_id, species_id, rarity, pet_name),
        )
        new_pet_id = cursor.lastrowid
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
        cursor = await db.execute(
            "INSERT INTO pets "
            "(owner_id, species_id, rarity, name, placement, fatigue, is_summoned, "
            "pet_level, duplicates_collected, copy_index) "
            "VALUES (?, ?, ?, ?, 'storage', 0, 0, 1, 1, ?)",
            (user_id, species_id, rarity, pet_name, next_index),
        )
        return {
            "outcome": "new_copy_created",
            "pet_id": cursor.lastrowid,
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

    # Wolf reduction from the level-curve, picks active/passive based on slot.
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

    # Unicorn reduction from the level-curve.
    unicorn_reduction = 0.0
    async with db.execute(
        "SELECT COALESCE(pet_level, 1) FROM pets WHERE owner_id = ? "
        "AND species_id = 'unicorn' AND placement IN ('active', 'passive') AND fatigue < 100 LIMIT 1",
        (user_id,)
    ) as c:
        row = await c.fetchone()
        if row:
            uni_bonus = UNICORN_BONUSES.get(max(1, min(10, row[0])), {})
            unicorn_reduction = min(
                uni_bonus.get("daily_fatigue_reduction", 0.0),
                UNICORN_REDUCTION_CAP,
            )

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
            await db.execute(
                "UPDATE pets SET last_fatigue_update = ? WHERE id = ?",
                (now_str, pet["id"])
            )
            continue

        try:
            last_dt = datetime.strptime(last_upd, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            await db.execute(
                "UPDATE pets SET last_fatigue_update = ? WHERE id = ?",
                (now_str, pet["id"])
            )
            continue

        # Cap elapsed time to prevent huge spikes for long-inactive users
        max_lag = timedelta(days=PET_MAX_FATIGUE_LAG_DAYS)
        if now - last_dt > max_lag:
            last_dt = now - max_lag

        base_rate = (
            PET_ACTIVE_FATIGUE_PER_DAY if pet["placement"] == "active"
            else PET_PASSIVE_FATIGUE_PER_DAY
        )
        effective_rate = base_rate * (1.0 - wolf_reduction)
        if unicorn_reduction > 0:
            effective_rate *= (1.0 - unicorn_reduction)

        if effective_rate <= 0:
            continue

        # How many fatigue points have accumulated since last update?
        seconds_per_point = 86400.0 / effective_rate
        elapsed_seconds = (now - last_dt).total_seconds()
        gain_int = int(elapsed_seconds / seconds_per_point)

        if gain_int > 0:
            new_fatigue = min(100, pet["fatigue"] + gain_int)
            # Advance the timer by exactly the seconds consumed (preserves fractional remainder)
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
        return 0.0

    try:
        last_dt = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return 0.0

    hours = (datetime.now() - last_dt).total_seconds() / 3600.0

    # Pull every hamster the user has in the nursery. Lv4+ also keeps earning at fatigue 100.
    async with db.execute(
        "SELECT COALESCE(pet_level, 1), fatigue FROM pets WHERE owner_id = ? "
        "AND species_id = 'hamster' AND placement IN ('active', 'passive')",
        (user_id,),
    ) as c:
        hamsters = await c.fetchall()

    total = 0.0
    for level, fatigue in hamsters:
        bonus = HAMSTER_BONUSES.get(max(1, min(10, level)), {})
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
        for _ in range(count):
            rand = random.randint(1, 100)
            cumulative = 0
            selected_rarity = "common"
            for rarity, chance in rates.items():
                cumulative += chance
                if rand <= cumulative:
                    selected_rarity = rarity
                    break
            species_id = random.choice(
                [s_id for s_id, s in PET_SPECIES.items() if s["rarity"] == selected_rarity]
            )

            result = await grant_duplicate(db, user_id, species_id)

            # Apply is_summoned flag to newly created copies only
            if is_summoned and result["outcome"] in ("first_copy_created", "new_copy_created"):
                await db.execute(
                    "UPDATE pets SET is_summoned = 1 WHERE id = ?", (result["pet_id"],)
                )

            result["species_id"] = species_id
            result["species_name"] = PET_SPECIES[species_id]["name"]
            results.append(result)

        await db.execute(
            "UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND item_id = ?",
            (count, user_id, egg_id)
        )
        await db.commit()
        return results
    except Exception:
        await db.rollback()
        raise
