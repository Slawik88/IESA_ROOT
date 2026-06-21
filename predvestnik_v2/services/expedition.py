# services/expedition.py
# Pure expedition reward calculation. No DB, no platform — only math and randomness.
import random

from core.constants import get_pet_bonus, scale_pet_bonus
from core.registry import EXPEDITIONS_DATA


def calculate_reward(
    hours: int,
    species_id: str | None = None,
    species_levels: dict | None = None,
    species_placements: dict | None = None,
    relic_mora_pct: float = 0.0,
) -> dict:
    """
    Calculate expedition outcome.

    Args:
        hours:           expedition duration (2/4/6/8)
        species_id:      species of the active pet (fox-specific perk applies here)
        species_levels:  dict {species_id: level} of all non-exhausted nursery pets.
                         Used for owl / falcon / fox bonuses. Missing key = 0 (no bonus).

    Returns:
        mora, xp, diamonds, extras (list of free items, e.g. treasure_map), buff_message
    """
    species_levels = species_levels or {}
    species_placements = species_placements or {}

    def _bonus(sp: str, lvl: int) -> dict:
        # Block 12: бонус с учётом слота (passive ×0.5, capstone off)
        return scale_pet_bonus(get_pet_bonus(sp, lvl), species_placements.get(sp))

    exp_data = EXPEDITIONS_DATA.get(hours)
    if not exp_data:
        return {"mora": 0, "xp": 0, "diamonds": 0, "extras": [], "buff_message": ""}

    mora = random.randint(exp_data["min_m"], exp_data["max_m"])
    xp = random.randint(exp_data["min_xp"], exp_data["max_xp"])
    base_mora = mora      # «база» до бонусов — для чека награды (БЛОК 3)
    base_xp = xp
    diamonds = 0
    extras: list[tuple[str, int]] = []
    buff_message = ""
    breakdown: list[dict] = []   # структурный чек: [{"label","mora","xp","diamonds","extra"}]

    # Falcon (any nursery slot): +mora_bonus, +xp_bonus, possibly double-loot chance,
    # plus a guaranteed Treasure Map on 8h trips at capstone Lv10.
    falcon_level = species_levels.get("falcon", 0)
    if falcon_level > 0:
        f = _bonus("falcon", falcon_level)
        m_bonus = f.get("mora_bonus", 0.0)
        x_bonus = f.get("xp_bonus", 0.0)
        m_gain = int(mora * m_bonus)
        x_gain = int(xp * x_bonus)

        if f.get("double_loot_chance", 0.0) > 0 and random.random() < f["double_loot_chance"]:
            m_gain += mora
            x_gain += xp
            buff_message += "\n🦅 <i>Сокол поймал двойную добычу!</i>"

        mora += m_gain
        xp += x_gain
        if m_gain or x_gain:
            buff_message += f"\n🦅 <i>Сокол (Ур.{falcon_level}): +{m_gain} Моры, +{x_gain} XP</i>"
            breakdown.append({"label": f"🦅 Сокол Ур.{falcon_level}", "mora": m_gain, "xp": x_gain})

        if hours == 8 and f.get("capstone_8h_treasure_map", False):
            extras.append(("treasure_map", 1))
            buff_message += "\n🦅 <i>Сокол нашёл Карту Сокровищ!</i>"
            breakdown.append({"label": "🦅 Сокол", "extra": "🗺 Карта Сокровищ"})

    # Fox on expedition: diamond rolls scale with duration (2h=1, 4h=2, 6h=3, 8h=4).
    # Per-roll chance depends on fox level. Capstone Lv10 adds chance of crystal egg.
    if species_id == "fox":
        fox_level = species_levels.get("fox", 1) or 1
        f = _bonus("fox", fox_level)
        chance = f.get("diamond_chance_per_2h", 0.0)
        rolls = max(1, hours // 2)
        for _ in range(rolls):
            if random.random() < chance:
                diamonds += 1
        if diamonds > 0:
            plural = "Алмаз" if diamonds == 1 else "Алмаза" if diamonds <= 4 else "Алмазов"
            buff_message += f"\n🦊 <i>Лиса нашла: <b>+{diamonds} {plural}!</b> 💎</i>"
            breakdown.append({"label": "🦊 Лиса", "diamonds": diamonds})

        crystal_chance = f.get("crystal_egg_chance", 0.0)
        if crystal_chance > 0 and random.random() < crystal_chance:
            extras.append(("egg_crystal", 1))
            buff_message += "\n🦊 <i>Лиса принесла Кристальное яйцо!</i>"
            breakdown.append({"label": "🦊 Лиса", "extra": "🥚 Кристальное яйцо"})

    # Owl (any nursery slot): +xp_bonus to expedition XP, scales with level.
    owl_level = species_levels.get("owl", 0)
    if owl_level > 0:
        o = _bonus("owl", owl_level)
        bonus_xp = int(xp * o.get("expedition_xp_bonus", 0.0))
        if bonus_xp > 0:
            xp += bonus_xp
            buff_message += f"\n🦉 <i>Сова (Ур.{owl_level}): +{bonus_xp} XP</i>"
            breakdown.append({"label": f"🦉 Сова Ур.{owl_level}", "xp": bonus_xp})

    # Block 13: суммарный бонус реликвий к моро-награде похода.
    if relic_mora_pct > 0:
        relic_gain = int(mora * relic_mora_pct)
        if relic_gain > 0:
            mora += relic_gain
            buff_message += f"\n🏛 <i>Реликвии: +{relic_gain} Моры (+{int(relic_mora_pct * 100)}%)</i>"
            breakdown.append({"label": f"🏛 Реликвии +{int(relic_mora_pct * 100)}%", "mora": relic_gain})

    return {
        "mora": mora,
        "xp": xp,
        "diamonds": diamonds,
        "extras": extras,
        "buff_message": buff_message,
        "base_mora": base_mora,   # для чека награды (БЛОК 3)
        "base_xp": base_xp,
        "breakdown": breakdown,
    }
