# services/combat_power.py — R1: Индекс Силы (⚡ CP), GDD_REBUILD_PLAN.md.
#
# CP — публичный «паспортный» показатель силы аккаунта:
#   уровень×100 + CP актив-питомца + 0.5×Σ CP пассивных + сет косметики + реликвии.
# Складские/аукционные питомцы CP не дают. Усталость НЕ учитывается (это паспорт,
# не боеготовность). Питомцовый CP выводится из тех же COMBAT_BASE_*-статов,
# что и Боёвка — единый источник силы.
from core.constants import (
    COMBAT_BASE_HP, COMBAT_BASE_STAMINA, COMBAT_BASE_ATK, COMBAT_BASE_DEF,
    COMBAT_LEVEL_SCALE,
    CP_PER_ACCOUNT_LEVEL, CP_PASSIVE_PET_SCALE, CP_PET_WEIGHTS,
    CP_PER_RELIC_POWER, CP_COSMETIC_SET_BONUS,
)
from core.registry import RELICS, RELIC_RARITY_META
from core.cosmetics import COSMETICS, COSMETIC_SLOTS, RARITY_ORDER


def pet_cp(rarity: str, level: int) -> int:
    """CP одного питомца из паспортных боевых статов (редкость + уровень)."""
    level = max(1, min(10, int(level or 1)))
    base = (
        COMBAT_BASE_ATK.get(rarity, 0) * CP_PET_WEIGHTS["atk"]
        + COMBAT_BASE_DEF.get(rarity, 0) * CP_PET_WEIGHTS["def"]
        + COMBAT_BASE_HP.get(rarity, 0) * CP_PET_WEIGHTS["hp"]
        + COMBAT_BASE_STAMINA.get(rarity, 0) * CP_PET_WEIGHTS["stamina"]
    )
    return int(round(base * (1.0 + COMBAT_LEVEL_SCALE * (level - 1))))


def _cosmetic_set_bonus(equipped: dict) -> int:
    """Бонус за ПОЛНЫЙ сет: все 6 носимых слотов заняты → CP по минимальной
    редкости из надетых предметов; любой пустой слот — 0."""
    min_rank = None
    for slot in COSMETIC_SLOTS:
        cid = equipped.get(slot)
        cos = COSMETICS.get(cid) if cid else None
        if not cos:
            return 0
        rank = RARITY_ORDER.get(cos.get("rarity", "common"), 0)
        min_rank = rank if min_rank is None else min(min_rank, rank)
    for rarity, rank in RARITY_ORDER.items():
        if rank == min_rank:
            return CP_COSMETIC_SET_BONUS.get(rarity, 0)
    return 0


async def calculate_cp(db, user_id: int) -> dict:
    """Полный расчёт CP с брейкдауном (для модалки «откуда цифра»).
    Возвращает {total, level_part, active_pet, passive_pets, cosmetics_set, relics}."""
    from infrastructure.repositories import users as users_repo
    from services.leveling import account_progress

    acc = await users_repo.get_account_progress(db, user_id)
    level = account_progress(acc.get("account_xp", 0))["level"]
    level_part = level * CP_PER_ACCOUNT_LEVEL

    active_part = 0
    passive_part = 0.0
    async with db.execute(
        "SELECT rarity, COALESCE(pet_level, 1) AS pet_level, placement "
        "FROM pets WHERE owner_id = ? AND placement IN ('active', 'passive')",
        (user_id,),
    ) as c:
        for row in await c.fetchall():
            cp = pet_cp(row["rarity"], row["pet_level"])
            if row["placement"] == "active":
                active_part += cp
            else:
                passive_part += cp * CP_PASSIVE_PET_SCALE

    async with db.execute(
        "SELECT slot, cosmetic_id FROM user_cosmetic_loadout WHERE user_id = ?",
        (user_id,),
    ) as c:
        equipped = {r["slot"]: r["cosmetic_id"] for r in await c.fetchall()}
    set_part = _cosmetic_set_bonus(equipped)

    relic_power = 0
    async with db.execute(
        "SELECT relic_id FROM user_relics WHERE user_id = ?", (user_id,)
    ) as c:
        for r in await c.fetchall():
            relic = RELICS.get(r["relic_id"])
            if relic:
                relic_power += RELIC_RARITY_META.get(relic["rarity"], {}).get("power", 0)
    relic_part = relic_power * CP_PER_RELIC_POWER

    total = int(round(level_part + active_part + passive_part + set_part + relic_part))
    return {
        "total": total,
        "level_part": level_part,
        "active_pet": int(active_part),
        "passive_pets": int(round(passive_part)),
        "cosmetics_set": set_part,
        "relics": relic_part,
    }


async def refresh_cp(db, user_id: int) -> int:
    """Пересчитать CP и записать в кэш users.combat_power (для топов/гейтов,
    где считать на лету дорого). Возвращает свежий total."""
    total = (await calculate_cp(db, user_id))["total"]
    await db.execute(
        "UPDATE users SET combat_power = ? WHERE user_tg_id = ?",
        (total, user_id),
    )
    return total