#!/usr/bin/env python3
"""Season 2 pass model: 60 days, points by real play time, daily norm with carry-over.

Old rules (shipped): Rhythm ~150 points/min, no cap, 30 x 300 points.
New rules: ~15 points per minute in any game, ranked x1.5, daily norm 300 at full
rate (unused norm carries over up to 3 days = 900), above the norm 20%.
Track: 40 levels, cheap start: levels 1-10 by 150 points, 11-40 by 285 (10 050 points).
Run: python3 tools/season2_pass_sim.py (pure model; the old column uses the
measured ~150 Rhythm points/min of tools/season2_rhythm_sim.py pass).
"""
from __future__ import annotations

import random
import statistics

DAYS = 60
NEW_LEVELS = 40
NEW_COSTS = [150] * 10 + [285] * 30          # points per level
NEW_TOTAL = sum(NEW_COSTS)
OLD_LEVELS, OLD_PER_LEVEL = 30, 300
NORM, CARRY_DAYS, OVER_RATE = 300, 3, 0.20
PPM_CASUAL, RANKED_MULT = 15, 1.5
# share, chance to play a day, minutes on a played day (mean), ranked minutes of those, mean days before quitting
CLASSES = {
    "casual": (0.55, 0.30, 10, 0, 40),
    "regular": (0.30, 0.65, 25, 10, 90),
    "hardcore": (0.15, 0.95, 55, 20, 400),
}


def level_of(points: float) -> int:
    level = 0
    for cost in NEW_COSTS:
        if points < cost:
            break
        points -= cost
        level += 1
    return level


def season(rng: random.Random, kind: str) -> tuple[int, int, int]:
    _, p_day, minutes, ranked, quit_mean = CLASSES[kind]
    quits = rng.expovariate(1 / quit_mean)
    new = old = 0.0
    bank = 0.0
    finished_day = None
    for day in range(DAYS):
        bank = min(NORM * CARRY_DAYS, bank + NORM)
        if day > quits or rng.random() >= p_day:
            continue
        m = max(2.0, rng.gauss(minutes, minutes * 0.35))
        r = min(m, ranked)
        raw = (m - r) * PPM_CASUAL + r * PPM_CASUAL * RANKED_MULT
        full = min(raw, bank)
        bank -= full
        new += full + (raw - full) * OVER_RATE
        old += m * 150
        if finished_day is None and new >= NEW_TOTAL:
            finished_day = day + 1
    return (level_of(new), min(OLD_LEVELS, int(old // OLD_PER_LEVEL)),
            finished_day or 0)


def main():
    rng = random.Random(20261024)
    print(f"{'class':>9} | {'new: level med (p10-p90)':>24} {'full 40':>7} {'finish day med':>14} | {'old: full 30 levels':>19}")
    for kind, (share, *_rest) in CLASSES.items():
        rows = [season(rng, kind) for _ in range(4000)]
        lv = sorted(r[0] for r in rows)
        fin = [r[2] for r in rows if r[2]]
        print(f"{kind:>9} | {statistics.median(lv):>8.0f} ({lv[len(lv) // 10]}-{lv[len(lv) * 9 // 10]}){'':>9} "
              f"{sum(l >= NEW_LEVELS for l in lv) / len(lv):>7.0%} {statistics.median(fin) if fin else 0:>14.0f} | "
              f"{sum(r[1] >= OLD_LEVELS for r in rows) / len(rows):>19.0%}")


if __name__ == "__main__":
    main()
