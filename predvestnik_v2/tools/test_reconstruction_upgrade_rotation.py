#!/usr/bin/env python3
"""Proof that inter-wave offers vary by seed without losing determinism."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.reconstruction import CLICKER_UPGRADES  # noqa: E402
from services import reconstruction_combat as combat  # noqa: E402


def first_offer(seed: int) -> tuple[str, ...]:
    state = combat.new_encounter(seed=seed)
    combat._complete_wave(state)
    return tuple(option["id"] for option in state["reward_options"])


catalog = set(CLICKER_UPGRADES)
seen_first: set[tuple[str, ...]] = set()
seen_second: set[tuple[str, ...]] = set()
frequency: Counter[str] = Counter()

for seed in range(1, 601):
    offer = first_offer(seed)
    assert offer == first_offer(seed), f"offer is not deterministic for seed {seed}"
    assert len(offer) == 3 and len(set(offer)) == 3
    assert set(offer) <= catalog
    seen_first.add(offer)
    frequency.update(offer)

    state = combat.new_encounter(seed=seed)
    combat._complete_wave(state)
    chosen = state["reward_options"][0]["id"]
    result = combat.apply_action(state, {"type": "choose_upgrade", "upgrade_id": chosen})
    assert result["ok"] and state["round"] == 2
    combat._complete_wave(state)
    second = tuple(option["id"] for option in state["reward_options"])
    assert len(second) == 3 and chosen not in second and len(set(second)) == 3
    seen_second.add(second)
    frequency.update(second)

assert set(frequency) == catalog
assert len(seen_first) >= 30, len(seen_first)
assert len(seen_second) >= 30, len(seen_second)
spread = max(frequency.values()) - min(frequency.values())
assert spread <= 120, frequency

lantern = combat.new_encounter(seed=77, companion_role_id="lantern")
combat._complete_wave(lantern)
assert len(lantern["reward_options"]) == 2

archivist = combat.new_encounter(seed=77, companion_role_id="archivist")
combat._complete_wave(archivist)
assert len(archivist["reward_options"]) == 2

echo = combat.new_encounter(seed=77, companion_role_id="echo")
echo["companion_state"]["echo_insight"] = 1
combat._complete_wave(echo)
assert len(echo["reward_options"]) == 4
assert len({option["id"] for option in echo["reward_options"]}) == 4

print(
    "reconstruction_upgrade_rotation: deterministic varied offers + companion trade-offs OK"
)
