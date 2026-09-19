#!/usr/bin/env python3
"""Pure policy proof for the approved 1–40 achievement horizon."""
from core import achievements_v1 as rules


def run() -> None:
    rules.validate()
    assert rules.lifetime_mora() == 515
    assert rules.MILESTONE_LEVELS == (1, 5, 10, 20, 30, 40)
    assert {definition["category"] for definition in rules.FAMILIES.values()} == {"games", "collection"}
    for family, definition in rules.FAMILIES.items():
        cap = int(definition["cap_events"])
        assert rules.unlocked_level(family, completed_events=cap, active_weeks=155) < 40
        assert rules.unlocked_level(family, completed_events=cap, active_weeks=156) == 40
        assert rules.event_threshold(family, 40) == cap
    assert rules.week_threshold(40) == 156
    assert rules.reward_mora(1) == 5 and rules.reward_mora(40) == 75
    print("OK: achievements v1 five families, milestones, three-year gate and Mora budget")


if __name__ == "__main__":
    run()
