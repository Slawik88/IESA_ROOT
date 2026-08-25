from core.constants import (
    WOLF_BONUSES, WOLF_REDUCTION_CAP, PET_PLACEMENT_FATIGUE_RESTORE,
    get_pet_bonus, PET_LEVEL_MILESTONE_REWARDS,
)


async def movement_fatigue_cost(db, user_id: int) -> int:
    """Цена усталости за перемещение питомца между слотами — ЕДИНАЯ формула
    для бота и сайта (раньше расходились: бот применял только скидку Волка,
    сайт — только Lv10-иммунитет и не брал цену за уход на склад).

    Правила (ровно как в описании вида Волк в registry):
      • базовая цена PET_PLACEMENT_FATIGUE_RESTORE за ЛЮБОЕ перемещение;
      • неистощённый Волк в питомнике даёт скидку по уровню (active/passive);
      • Волк Lv10 — «иммунитет перемещений»: цена 0."""
    async with db.execute(
        "SELECT placement, COALESCE(pet_level, 1) FROM pets "
        "WHERE owner_id = ? AND species_id = 'wolf' "
        "AND placement IN ('active', 'passive') AND fatigue < 100 LIMIT 1",
        (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return PET_PLACEMENT_FATIGUE_RESTORE
    placement, level = row[0], max(1, min(10, row[1]))
    bonus = WOLF_BONUSES.get(level, {})
    if bonus.get("movement_immunity"):
        return 0
    reduction = min(
        bonus.get("active_reduction" if placement == "active" else "passive_reduction", 0.0),
        WOLF_REDUCTION_CAP,
    )
    return int(PET_PLACEMENT_FATIGUE_RESTORE * (1.0 - reduction))


async def get_wolf_fatigue_reduction(db, user_id: int) -> float:
    """Fatigue reduction factor from the user's wolf (whichever slot it's in).
    Exhausted wolves (fatigue=100) give nothing. Capped at WOLF_REDUCTION_CAP."""
    async with db.execute(
        "SELECT placement, COALESCE(pet_level, 1) FROM pets "
        "WHERE owner_id = ? AND species_id = 'wolf' "
        "AND placement IN ('active', 'passive') AND fatigue < 100 LIMIT 1",
        (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return 0.0
    placement, level = row[0], row[1]
    bonus = WOLF_BONUSES.get(max(1, min(10, level)), {})
    reduction = (
        bonus.get("active_reduction", 0.0)
        if placement == "active"
        else bonus.get("passive_reduction", 0.0)
    )
    return min(reduction, WOLF_REDUCTION_CAP)


async def is_wolf_active_slot(db, user_id: int) -> bool:
    """True when a non-exhausted wolf is specifically in the active slot."""
    async with db.execute(
        "SELECT 1 FROM pets WHERE owner_id = ? AND species_id = 'wolf' "
        "AND placement = 'active' AND fatigue < 100 LIMIT 1",
        (user_id,)
    ) as cursor:
        return await cursor.fetchone() is not None


async def get_active_wolf_food_extra(db, user_id: int) -> int:
    """Extra fatigue restored per food when wolf is in the active slot."""
    async with db.execute(
        "SELECT COALESCE(pet_level, 1) FROM pets WHERE owner_id = ? "
        "AND species_id = 'wolf' AND placement = 'active' AND fatigue < 100 LIMIT 1",
        (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return 0
    return WOLF_BONUSES.get(max(1, min(10, row[0])), {}).get("food_extra", 0)


def format_pet_bonus_short(species_id: str, level: int) -> str:
    """One-line bonus blurb for the species at a given level. Used in profile and pet card."""
    b = get_pet_bonus(species_id, level)
    if not b:
        return ""

    if species_id == "hamster":
        parts = [f"💰 +{b['mora_per_hour']} Моры/ч · кап {b['cap']}"]
        if b.get("ignore_exhaustion"):
            parts.append("работает при 100 усталости")
        if b.get("daily_diamond", 0) > 0:
            parts.append(f"+{b['daily_diamond']} 💎/сутки")
        return " · ".join(parts)

    if species_id == "squirrel":
        return f"🐿 +{int(b.get('quest_mora_bonus', 0) * 100)}% Моры за квесты"

    if species_id == "owl":
        return "📚 Архивная способность сохранена · бонус за сообщения не действует"

    if species_id == "dog":
        parts = [f"⚡ −{int(b['speed_reduction'] * 100)}% длит. экспедиций"]
        if b.get("self_fatigue_reduction", 0) > 0:
            parts.append(f"собаке −{int(b['self_fatigue_reduction'] * 100)}% усталость в походе")
        if b.get("zero_fatigue_chance", 0) > 0:
            parts.append(f"{int(b['zero_fatigue_chance'] * 100)}% шанс 0 усталости")
        if b.get("expedition_cost_reduction", 0) > 0:
            parts.append(f"−{int(b['expedition_cost_reduction'] * 100)}% стоимость похода")
        return " · ".join(parts)

    if species_id == "turtle":
        parts = [f"🛒 −{int(b['shop_discount'] * 100)}% магазин"]
        if b.get("expedition_discount", 0) > 0:
            parts.append(f"−{int(b['expedition_discount'] * 100)}% поход")
        if b.get("gacha_daily_discount", 0) > 0:
            parts.append(f"−{int(b['gacha_daily_discount'] * 100)}% крутка/день")
        return " · ".join(parts)

    if species_id == "falcon":
        parts = [f"🦅 +{int(b['mora_bonus'] * 100)}% Мора похода"]
        if b.get("xp_bonus", 0) > 0:
            parts.append(f"+{int(b['xp_bonus'] * 100)}% XP")
        if b.get("double_loot_chance", 0) > 0:
            parts.append(f"{int(b['double_loot_chance'] * 100)}% двойн. добыча")
        if b.get("capstone_8h_treasure_map"):
            parts.append("8ч → Карта Сокровищ")
        return " · ".join(parts)

    if species_id == "wolf":
        parts = [f"🐺 −{int(b['passive_reduction'] * 100)}% усталость пасс."]
        if b.get("active_reduction", 0) > 0:
            parts.append(f"−{int(b['active_reduction'] * 100)}% актив")
        if b.get("food_extra", 0) > 0:
            parts.append(f"корм +{b['food_extra']}")
        if b.get("daily_restore_uses", 0) > 0:
            parts.append(f"{b['daily_restore_uses']}× в день восстановить {b['daily_restore_amount']}")
        if b.get("movement_immunity"):
            parts.append("иммунитет к перемещениям")
        return " · ".join(parts)

    if species_id == "fox":
        parts = [f"💎 {int(b['diamond_chance_per_2h'] * 100)}% шанс 💎/2ч"]
        if b.get("common_dup_bonus", 0) > 0:
            parts.append(f"+{int(b['common_dup_bonus'] * 100)}% Common-дуб. из гачи")
        if b.get("weekly_guaranteed_diamond"):
            parts.append("гарант. 💎/нед.")
        if b.get("crystal_egg_chance", 0) > 0:
            parts.append(f"{int(b['crystal_egg_chance'] * 100)}% 🎟 Алмазный Жетон")
        return " · ".join(parts)

    if species_id == "dragon":
        parts = [f"🏦 +{int(b['bank_bonus'])} к банку"]
        if b.get("free_food_chance", 0) > 0:
            parts.append(f"{int(b['free_food_chance'] * 100)}% беспл. корм")
        if b.get("hamster_collect_bonus", 0) > 0:
            parts.append(f"+{int(b['hamster_collect_bonus'])} Моры при сборе хомяков")
        if b.get("weekly_bank_grant", 0) > 0:
            parts.append(f"+{int(b['weekly_bank_grant'])}/нед. в банк")
        return " · ".join(parts)

    if species_id == "unicorn":
        parts = [f"🌟 −{int(b['daily_fatigue_reduction'] * 100)}% суточная усталость"]
        if b.get("immunity_uses", 0) > 0:
            parts.append(f"{b['immunity_uses']}×{b['immunity_hours']}ч иммунитет/день")
        if b.get("active_recovery_per_hour", 0) > 0:
            parts.append(f"актив. восст. {b['active_recovery_per_hour']}/ч")
        if b.get("auto_recover"):
            parts.append("auto-восст. при 100")
        return " · ".join(parts)

    return ""


async def apply_pet_milestones(
    db,
    user_id: int,
    pet_id: int,
    milestones_unlocked: list[int],
) -> list[dict]:
    """Grant one-time milestone rewards for newly reached pet levels.
    Skips milestones already recorded for this pet.
    Returns a list of granted milestone dicts (for notification).
    No commit — caller handles the transaction.
    """
    from infrastructure.repositories.zoo import get_pet_milestones_received, record_pet_milestone
    from infrastructure.repositories.economy import add_balance

    if not milestones_unlocked:
        return []

    already_received = await get_pet_milestones_received(db, pet_id)
    granted = []

    for level in milestones_unlocked:
        if level in already_received:
            continue
        reward = PET_LEVEL_MILESTONE_REWARDS.get(level)
        if not reward:
            continue

        if reward["mora"] > 0:
            await add_balance(db, user_id, mora=reward["mora"], source="pet_milestone", commit=False)
        if reward["diamonds"] > 0:
            await add_balance(db, user_id, diamonds=reward["diamonds"], source="pet_milestone", commit=False)
        for item_id, qty in reward.get("items", ()):
            await db.execute(
                "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
                (user_id, item_id, qty, qty),
            )

        await record_pet_milestone(db, pet_id, level)
        granted.append({"level": level, "reward": reward})

    return granted
