# services/combat_power.py — legacy Индекс Силы (⚡ CP), retirement LCB-001.
#
# Боёвка 3.0: CP — публичный «паспортный» показатель силы аккаунта:
#   уровень×100 + Σ CP юнитов отряда + 0.25×Σ CP юнитов вне отряда
#   + 0.1×Σ pet_cp мирной коллекции + сет косметики + реликвии.
# Мирные питомцы больше не сражаются, но коллекция даёт маленький пассивный
# бонус (не обесценивать прокачанное). pet_cp сохранён для этого бонуса
# и для одноразовой компенсации (services/barracks.py).
from core.constants import (
    COMBAT_BASE_HP, COMBAT_BASE_STAMINA, COMBAT_BASE_ATK, COMBAT_BASE_DEF,
    COMBAT_LEVEL_SCALE,
    CP_PER_ACCOUNT_LEVEL, CP_PET_WEIGHTS,
    CP_PER_RELIC_POWER, CP_COSMETIC_SET_BONUS,
    CP_UNIT_RESERVE_SCALE, CP_PET_COLLECTION_SCALE,
)
from core.registry import RELICS, RELIC_RARITY_META
from core.cosmetics import COSMETICS, COSMETIC_SLOTS, RARITY_ORDER
from core.units import unit_cp


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
    Возвращает {total, level_part, squad_units, reserve_units, pet_collection,
    cosmetics_set, relics} (+легаси-ключи active_pet/passive_pets для фронта)."""
    from infrastructure.repositories import users as users_repo
    from infrastructure.repositories import units as u_repo
    from services.leveling import account_progress

    acc = await users_repo.get_account_progress(db, user_id)
    level = account_progress(acc.get("account_xp", 0))["level"]
    level_part = level * CP_PER_ACCOUNT_LEVEL

    # Боёвка 3.0: юниты (отряд — полностью, резерв — частично)
    squad_part = 0
    reserve_part = 0.0
    try:
        squad_ids = set((await u_repo.get_squad(db, user_id)).values())
        for r in await u_repo.get_units(db, user_id):
            if int(r["level"]) < 1:
                continue
            cp = unit_cp(r["unit_id"], int(r["level"]))
            if r["unit_id"] in squad_ids:
                squad_part += cp
            else:
                reserve_part += cp * CP_UNIT_RESERVE_SCALE
    except Exception:
        pass  # таблиц ещё нет (первый старт до init_db)

    # Мирная коллекция: маленький пассивный бонус
    collection_part = 0.0
    async with db.execute(
        "SELECT rarity, COALESCE(pet_level, 1) AS pet_level "
        "FROM pets WHERE owner_id = ? AND placement IN ('active', 'passive')",
        (user_id,),
    ) as c:
        for row in await c.fetchall():
            collection_part += pet_cp(row["rarity"], row["pet_level"]) * CP_PET_COLLECTION_SCALE

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

    total = int(round(level_part + squad_part + reserve_part + collection_part
                      + set_part + relic_part))
    return {
        "total": total,
        "level_part": level_part,
        "squad_units": int(squad_part),
        "reserve_units": int(round(reserve_part)),
        "pet_collection": int(round(collection_part)),
        # легаси-ключи (старый фронт показывал питомцев) — теперь юниты/коллекция
        "active_pet": int(squad_part),
        "passive_pets": int(round(reserve_part + collection_part)),
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
