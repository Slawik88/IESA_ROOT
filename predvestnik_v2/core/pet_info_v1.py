"""Everything a player can learn about one pet species. Pure data assembled from the live rules: no numbers
of its own, so the screen can never disagree with the game."""
from __future__ import annotations

from core.chests_v1 import CARD_RARITY_WEIGHTS, PET_SPECIES
from core.pet_levels_v1 import total_cost
from core.pet_routes_v1 import HINT_MIN_LEVEL, SCOUT_MIN_LEVEL
from core.pets_v1 import MAX_LEVEL, level_effects
from core.pets_v2 import SPECIES as TRAIL_SPECIES

TERRAIN_NAMES = {"forest": "Лес", "pass": "Перевал", "ruins": "Руины", "swamp": "Болото", "any": "любая местность"}
FIND_NAMES = {
    "treat": "лакомства", "mora": "Мора", "talisman": "талисманы", "diamond": "алмазы",
    "essence": "Эссенция", "bonus_xp": "дополнительный опыт",
}


def card_sources(rarity: str) -> list[dict]:
    """Chest stars at which a card of this rarity can drop, with the share of cards of that rarity."""
    return [
        {"stars": int(stars), "percent": int(weights[rarity])}
        for stars, weights in sorted(CARD_RARITY_WEIGHTS.items()) if rarity in weights
    ]


def level_milestones() -> list[dict]:
    """What a level adds, read from level_effects (the same function the expeditions use)."""
    top = level_effects(MAX_LEVEL)
    return [
        {"level": 2, "text": f"Бонус награды маршрута растёт на 1% за уровень, до +{top['expedition_route_bonus_percent']}% на {MAX_LEVEL} уровне"},
        {"level": HINT_MIN_LEVEL, "text": "Питомец показывает шансы маршрутов экспедиции до выбора"},
        {"level": 8, "text": "Лучше шансы маршрутов: +5 процентных пунктов"},
        {"level": SCOUT_MIN_LEVEL, "text": "Открывается маршрут «Разведка»"},
        {"level": MAX_LEVEL, "text": "Максимальный облик"},
    ]


def species_info(species_id: str) -> dict:
    species = PET_SPECIES[species_id]
    rarity = str(species["rarity"])
    cost = total_cost(rarity)
    trail = TRAIL_SPECIES.get(species_id)
    traits = None
    if trail:
        _, terrain, energy_bonus, rest_bonus, find = trail
        traits = {
            "favorite_route": TERRAIN_NAMES.get(terrain, terrain),
            "energy_bonus": int(energy_bonus),
            "rest_bonus": int(rest_bonus),
            "favored_find": FIND_NAMES.get(find, find),
        }
    return {
        "card_sources": card_sources(rarity),
        "level_cost": {"cards": cost.cards, "mora": cost.mora, "essence": cost.essence, "max_level": MAX_LEVEL},
        "trail_traits": traits,
        # feature: the flag that gates it; the screen marks a use as "soon" while the flag is off
        "uses": [
            {"text": "Поход: ключ сундука за возвращение", "feature": None},
            {"text": "Экспедиция: выбор маршрута и ключи", "feature": None},
            {"text": "Экспедиция: награда Морой за маршрут", "feature": "route_rewards"},
            {"text": "Улучшение уровня за карты, Мору и Эссенцию", "feature": "level_up"},
            {"text": "Тропа: особенности вида", "feature": "trail"},
        ],
    }
