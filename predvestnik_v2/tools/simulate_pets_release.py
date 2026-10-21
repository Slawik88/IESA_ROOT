"""Reproducible release diagnostics using actual production rules, no DB writes.

Synthetic cases are uniform coverage, NOT forecasts of player behaviour or
inflation. SQL transition/replay proofs live in test_pets_v2_pg.py.
Run with PYTHONPATH=. python tools/simulate_pets_release.py [--output file.json].
"""
from datetime import datetime, timedelta
import argparse
import json
from math import isclose
from random import Random
from statistics import mean

from core import pets_v2 as rules, minesweeper_v2 as mine
from services.pets_v2 import _rest, _build


def simulate() -> dict:
    rng = Random(20261021)
    now = datetime(2026, 10, 21, 12)
    restored = []
    cases = 0
    # All species, levels, camp levels, energy-cap builds and energy points.
    # Verify that settling rest at intermediate actions never changes totals.
    for species in rules.SPECIES:
        for level in range(1, 31):
            for lounge in range(6):
                for traits in ([], ["hardy"]):
                    for fraction in (0, .25, .75, 1):
                        build = _build({"traits": traits}, [], {"lounge": lounge})
                        cap = rules.energy_max(level, species, 15 if traits else 0)
                        state = dict(level=level, energy=cap*fraction, energy_at=now)
                        pet = dict(species_id=species)
                        first, second = rng.uniform(0, 24), rng.uniform(0, 24)
                        middle = _rest(state, pet, now+timedelta(hours=first), build)
                        total = _rest(state, pet, now+timedelta(hours=first+second), build)
                        split = _rest({**state, "energy": middle, "energy_at": now+timedelta(hours=first)}, pet,
                                      now+timedelta(hours=first+second), build)
                        assert isclose(total, split, abs_tol=1e-8)
                        assert state["energy"] <= total <= cap
                        # The old pair/trial writer reset energy_at while saving
                        # stale energy. Quantify the rest that is now preserved.
                        restored.append(total-state["energy"])
                        cases += 1
    # Demonstrate naturally occurring automatic easy wins independently of UI.
    auto = 0
    spec = mine.difficulty("easy")
    for seed in range(10000):
        layout = mine.board(seed.to_bytes(32, "big"), spec, 14, ruleset_version=mine.LEGACY_RULESET_VERSION)
        _, _, status, _ = mine.apply_action(spec=spec, layout=layout, revealed=set(), flags=set(), kind="open", cell=14)
        if status == "won":
            auto += 1
            assert not mine.speed_ranked(status=status, opened_actions=1, elapsed_ms=0)
    return {
        "seed": 20261021,
        "scope": "actual rules + service rest, synthetic uniform coverage; no player population or economy forecast",
        "rest_cases": cases, "rest_invariant_failures": 0,
        "preserved_energy_per_case_mean": round(mean(restored), 4),
        "preserved_energy_per_case_max": round(max(restored), 4),
        "minesweeper_boards": 10000, "first_cell": 14,
        "automatic_valid_wins": auto, "automatic_speed_ranked": 0,
        "economy_policy": "prices, drops, XP caps, rewards and paid mechanics unchanged",
        "new_gear_or_mode": "design proposal only; not implemented or simulated as released content",
        "hypothetical_five_identical_talismans": {
            str(tier): {
                "current_two_xp_mult": round((1+plus)**2*(1+rules.TALISMAN_SET_BONUS), 6),
                "hypothetical_five_xp_mult": round((1+plus)**5*(1+rules.TALISMAN_SET_BONUS), 6),
            } for tier, plus in rules.TALISMAN_PLUS.items()
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    result = simulate()
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(encoded+"\n", encoding="utf-8")
    print(encoded)
