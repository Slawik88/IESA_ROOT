"""Pet level-ups paid with currencies (ECO-04, P7). Pure rules: no clock, no database.

One step L -> L+1 costs species Pet Cards and Mora, and the steps that enter L5 / L10 / L15
cost Essence as well. Cards of a Common or Rare pet add up to the owner-fixed 89 586 for L1 -> L16.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from core.pets_v1 import MAX_LEVEL, PetPolicyError


POLICY_VERSION: Final = "pet-levels-v1-2026-10-13"
FLAG: Final = "pets_level_up_v1"
REASON_CODE: Final = "pet_level_up"
CARDS_TOTAL_COMMON: Final = 89_586

# index 0 is the step 1 -> 2, index 14 is the step 15 -> 16
CARDS_PER_STEP: Final = (
    70, 290, 650, 1160, 1810, 2600, 3540, 4620, 5850, 7220, 8740, 10400, 12210, 14160, 16266,
)
MORA_PER_STEP: Final = (6, 19, 36, 58, 82, 110, 141, 175, 211, 250, 291, 334, 380, 428, 479)
ESSENCE_ON_ENTERING: Final = {5: 20, 10: 60, 15: 150}

# Mora is scaled by rarity; Epic and Legendary pets need fewer cards because their cards are scarcer.
MORA_MULTIPLIER: Final = {"common": 1.0, "uncommon": 1.1, "rare": 1.25, "epic": 1.5, "legendary": 1.8}
CARDS_MULTIPLIER: Final = {"common": 1.0, "uncommon": 1.0, "rare": 1.0, "epic": 0.7, "legendary": 0.5}


@dataclass(frozen=True, slots=True)
class LevelCost:
    level_before: int
    level_after: int
    cards: int
    mora: int
    essence: int


def level_up_cost(level: int, rarity: str) -> LevelCost:
    """Price of the step ``level`` -> ``level + 1`` for a pet of ``rarity``."""
    if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level < MAX_LEVEL:
        raise PetPolicyError("Питомец уже на максимальном уровне.")
    rarity = str(rarity or "")
    if rarity not in CARDS_MULTIPLIER:
        raise PetPolicyError("Неизвестная редкость питомца.")
    step = level - 1
    return LevelCost(
        level_before=level, level_after=level + 1,
        cards=max(1, round(CARDS_PER_STEP[step] * CARDS_MULTIPLIER[rarity])),
        mora=max(1, round(MORA_PER_STEP[step] * MORA_MULTIPLIER[rarity])),
        essence=ESSENCE_ON_ENTERING.get(level + 1, 0),
    )


def total_cost(rarity: str) -> LevelCost:
    """Whole path L1 -> L16, for tests and the shop screen."""
    steps = [level_up_cost(level, rarity) for level in range(1, MAX_LEVEL)]
    return LevelCost(1, MAX_LEVEL, sum(s.cards for s in steps), sum(s.mora for s in steps), sum(s.essence for s in steps))
