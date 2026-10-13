#!/usr/bin/env python3
"""Chest keys up, chest loot down: weekly income before/after for player archetypes.

Pure arithmetic on core.chests_v1 tables (no DB). Key income per source is a policy
number; archetype behaviour (runs per day, VIP, paid keys) is an explicit assumption
printed with the result, not a measurement.
Run: python3 tools/chests_keys_rebalance_sim.py [--json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core.chests_v1 as c  # noqa: E402

OLD_KEYS = {"daily_set": 1, "weekly_set": 1, "trek": 1, "expedition": 1, "vip_daily": 1}
NEW_KEYS = {"daily_set": 2, "weekly_set": 3, "trek": 1, "expedition": 2, "vip_daily": 2}

# Real grant rules (not "every action pays"):
#  - VIP: a key only on every 7th daily-mission completion -> 1 milestone per 7 days.
#  - Pets: the simulated pet-key events follow pets v1 amounts (walk 1, expedition 2). Pets v2
#    (flag pets_v2, off) has its own limits, 2 keys/day and 5/week, and is NOT changed by ECO-02;
#    the 5-events/week cap here is that v2 ceiling used as a conservative upper bound.
PET_KEY_EVENTS_CAP_PER_WEEK = 5
# per week: daily sets, weekly sets, treks, expeditions, vip milestones
ARCHETYPES = {
    "Лёгкий (задания + 1 поход в день)": dict(daily_set=7, weekly_set=1, trek=5, expedition=0, vip_daily=0),
    "Активный (походы и экспедиции до лимита 5 в неделю)": dict(daily_set=7, weekly_set=1, trek=2, expedition=3, vip_daily=0),
    "Активный с VIP": dict(daily_set=7, weekly_set=1, trek=2, expedition=3, vip_daily=1),
}
for _name, _use in ARCHETYPES.items():
    assert _use["trek"] + _use["expedition"] <= PET_KEY_EVENTS_CAP_PER_WEEK, _name

# Tables as they were before ECO-02 (the live core now holds the new ones).
OLD_TABLES = dict(
    mora={1: (18, 28), 2: (28, 42), 3: (45, 65), 4: (65, 95), 5: (95, 140),
          6: (140, 210), 7: (220, 320), 8: (340, 500), 9: (600, 900), 10: (1200, 1800)},
    diamonds={5: (1, 1), 6: (1, 2), 7: (1, 2), 8: (2, 3), 9: (3, 5), 10: (5, 8)},
    zarniki={9: (10, 30), 10: (30, 50)},
    cards={3: 550, 4: 1100, 5: 2200, 6: 4400, 7: 8800, 8: 13200, 9: 22000, 10: 33000},
    jokers={5: 1, 6: 2, 7: 3, 8: 5, 9: 8, 10: 12},
    reward_weights={
        1: {"mora": 70, "food": 30}, 2: {"mora": 55, "food": 45},
        3: {"mora": 15, "food": 20, "pet_card": 65}, 4: {"mora": 15, "food": 10, "pet_card": 75},
        5: {"mora": 17, "diamonds": 8, "pet_card": 67, "joker": 8},
        6: {"mora": 15, "diamonds": 10, "pet_card": 66, "joker": 9},
        7: {"mora": 10, "diamonds": 10, "pet_card": 67, "joker": 13},
        8: {"mora": 8, "diamonds": 12, "pet_card": 68, "joker": 12},
        9: {"mora": 10, "diamonds": 15, "zarniki": 10, "pet_card": 50, "joker": 15},
        10: {"mora": 5, "diamonds": 10, "zarniki": 10, "pet_card": 50, "joker": 18, "vip_reward": 7},
    },
)
NEW_TABLES = dict(
    mora=c.MORA_RANGES, diamonds=c.DIAMOND_RANGES, zarniki=c.ZARNIKI_RANGES,
    cards=c.CARD_AMOUNTS, jokers=c.JOKER_AMOUNTS, reward_weights=c.REWARD_WEIGHTS,
)


def per_chest(mora, diamonds, zarniki, cards, jokers, reward_weights=None) -> dict[str, float]:
    out = dict(mora=0.0, diamonds=0.0, zarniki=0.0, cards=0.0, jokers=0.0, food=0.0, vip_days=0.0)
    weights = reward_weights or c.REWARD_WEIGHTS
    total = sum(c.STAR_WEIGHTS.values())
    for stars, star_weight in c.STAR_WEIGHTS.items():
        for kind, weight in weights[stars].items():
            p = star_weight / total * weight / 100
            if kind == "mora":
                out["mora"] += p * sum(mora[stars]) / 2
            elif kind == "diamonds":
                out["diamonds"] += p * sum(diamonds[stars]) / 2
            elif kind == "zarniki":
                out["zarniki"] += p * sum(zarniki[stars]) / 2
            elif kind == "pet_card":
                out["cards"] += p * cards[stars]
            elif kind == "joker":
                out["jokers"] += p * jokers[stars]
            elif kind == "food":
                out["food"] += p
            elif kind == "vip_reward":
                out["vip_days"] += p * c.VIP_DAYS
    return out


def weekly_keys(table: dict, usage: dict) -> float:
    return sum(table[k] * usage[k] for k in table)


def main() -> dict:
    old = per_chest(**OLD_TABLES)
    new = per_chest(**NEW_TABLES)
    result = {"per_chest_old": old, "per_chest_new": new, "archetypes": {}}
    for name, usage in ARCHETYPES.items():
        k_old, k_new = weekly_keys(OLD_KEYS, usage), weekly_keys(NEW_KEYS, usage)
        row = {"keys_old": k_old, "keys_new": k_new, "week": {}}
        for kind in old:
            a, b = k_old * old[kind], k_new * new[kind]
            row["week"][kind] = {"old": a, "new": b, "delta_pct": (b / a - 1) * 100 if a else 0.0}
        result["archetypes"][name] = row
    return result


if __name__ == "__main__":
    data = main()
    if "--json" in sys.argv:
        print(json.dumps(data, ensure_ascii=False, indent=1))
        raise SystemExit
    print("Один сундук, среднее (было -> стало)")
    for kind in data["per_chest_old"]:
        a, b = data["per_chest_old"][kind], data["per_chest_new"][kind]
        print(f"  {kind:9s} {a:10.3f} -> {b:10.3f}  ({(b / a - 1) * 100:+.0f}%)" if a else f"  {kind}: 0")
    for name, row in data["archetypes"].items():
        print(f"\n{name}: ключей в неделю {row['keys_old']:.0f} -> {row['keys_new']:.0f} ({(row['keys_new'] / row['keys_old'] - 1) * 100:+.0f}%)")
        for kind, v in row["week"].items():
            print(f"  {kind:9s} {v['old']:11.1f} -> {v['new']:11.1f}  ({v['delta_pct']:+.0f}%)")
