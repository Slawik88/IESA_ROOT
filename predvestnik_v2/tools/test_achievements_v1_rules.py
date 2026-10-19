#!/usr/bin/env python3
"""Pure policy proof for the approved 1–40 achievement horizon."""
from core import achievements_v1 as rules


def run() -> None:
    rules.validate()
    assert rules.lifetime_mora() == 515
    assert rules.MILESTONE_LEVELS == (1, 5, 10, 20, 30, 40)
    assert {definition["category"] for definition in rules.FAMILIES.values()} == {"games", "collection", "progression"}
    for family, definition in rules.FAMILIES.items():
        if 'thresholds' in definition:
            targets = definition['thresholds']
            assert all(a < b for a,b in zip(targets, targets[1:]))
            assert rules.unlocked_level(family,completed_events=targets[-1],active_weeks=0)==len(targets)
            for i,target in enumerate(targets,1):
                assert rules.unlocked_level(family,completed_events=target-1,active_weeks=0)==i-1
                assert rules.unlocked_level(family,completed_events=target,active_weeks=0)==i
            continue
        cap = int(definition["cap_events"])
        assert rules.unlocked_level(family, completed_events=cap, active_weeks=155) < 40
        assert rules.unlocked_level(family, completed_events=cap, active_weeks=156) == 40
        assert rules.event_threshold(family, 40) == cap
    assert sum(rules.reward_mora(l) for f in ('care','builder','stylist','quester') for l in range(1,rules.max_level(f)+1))==140
    assert sum(rules.max_level(f) for f in rules.FAMILIES)==228
    assert rules.week_threshold(40) == 156
    assert rules.reward_mora(1) == 5 and rules.reward_mora(40) == 75
    print("OK: achievements v1 five preserved paths, four finite life series, exact thresholds and bounded Mora budget")


if __name__ == "__main__":
    run()
