"""Pet info is assembled from the live rules for every species and never invents numbers."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.chests_v1 import CARD_RARITY_WEIGHTS, PET_SPECIES
from core.pet_info_v1 import level_milestones, species_info
from core.pet_levels_v1 import total_cost
from core.pets_v2 import SPECIES as TRAIL

assert set(PET_SPECIES) == set(TRAIL), "every bestiary species has Trail traits"
for species_id, row in PET_SPECIES.items():
    info = species_info(species_id)
    assert info["card_sources"], f"{species_id}: a card source is always shown"
    assert all(CARD_RARITY_WEIGHTS[s["stars"]][row["rarity"]] == s["percent"] for s in info["card_sources"])
    cost = total_cost(row["rarity"])
    assert info["level_cost"]["cards"] == cost.cards and info["level_cost"]["mora"] == cost.mora
    assert info["trail_traits"] and info["trail_traits"]["favored_find"]
    assert {u["feature"] for u in info["uses"]} <= {None, "route_rewards", "level_up", "trail"}
assert [m["level"] for m in level_milestones()] == [2, 4, 8, 12, 16]
print("OK: pet info covers every species from the live rules")
