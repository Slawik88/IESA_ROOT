#!/usr/bin/env python3
"""First-pass gift rebalance for season 2: does it narrow the spread of gift values?

Run: PYTHONPATH=. python3 tools/season2_rhythm_gifts_sim.py
Patches core.rhythm_v2 in memory only and repeats the forced-first-gift
experiment of tools/season2_rhythm_sim.py for the shipped and the proposed pool.
The proposal also caps the summed score bonus at MAX_SCORE_PCT.
"""
from __future__ import annotations

import dataclasses
import os
import random
import statistics
import sys
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import rhythm_v2 as R  # noqa: E402
import season2_rhythm_sim as S  # noqa: E402

SHIPPED = R.PERKS
CHANGES = {
    "vampire": dict(regen_every=30, score_pct=-22, max_stack=1),
    "echo_chain": dict(combo_step=2, combo_cap=40),
    "sprint": dict(score_pct=24),
    "steady_hand": dict(wrong_extra=0, score_pct=-12),
    "gold_vein": dict(score_pct=45),
    "glass_cannon": dict(score_pct=50),
    "iron_heart": dict(window_pct=-6),
    "stone_shield": dict(score_pct=-6),
    "tailwind": dict(score_pct=-12),
    "ebb_tide": dict(pace_pct=4),
    "second_wind": dict(score_pct=-5),
    "last_spark": dict(low_health_bonus_pct=48),
}
MAX_SCORE_PCT = 80
_shipped_score = R.score_for_correct


def capped_score(*, elapsed_ms, allowed_window_ms, combo_before, perks=None, health=R.BASE_HEALTH):
    """core.rhythm_v2.score_for_correct with an upper bound on the summed bonus."""
    perks = perks or R.new_perks()
    tier = 0 if elapsed_ms * 3 <= allowed_window_ms else 1 if elapsed_ms * 3 <= allowed_window_ms * 2 else 2
    timing = (100, 70, 45)[tier]
    if R._any(perks, "sharp_eye"):
        timing = timing * 3 // 2 if tier == 0 else timing // 2 if tier == 2 else timing
    step = R.COMBO_STEP + R._total(perks, "combo_step")
    cap = R.COMBO_CAP + R._total(perks, "combo_cap")
    raw = (timing + min(cap, combo_before * step)) * (3 if perks["bloody"] > 0 else 1)
    bonus = sum(item.cadence_bonus_pct * count for key, count in perks["owned"].items()
                if (item := R._PERK_BY_ID[key]).cadence_every and (combo_before + 1) % item.cadence_every == 0)
    if health <= 2:
        bonus += R._total(perks, "low_health_bonus_pct")
    percent = min(MAX_SCORE_PCT, max(R.MIN_SCORE_PCT, R._total(perks, "score_pct") + bonus))
    return max(1, raw * (100 + percent) // 100)


def use(pool_name: str) -> None:
    proposed = pool_name == "proposed"
    perks = tuple(dataclasses.replace(p, **CHANGES.get(p.id, {})) for p in SHIPPED) if proposed else SHIPPED
    R.score_for_correct = capped_score if proposed else _shipped_score
    R.PERKS = perks
    R._PERK_BY_ID.clear()
    R._PERK_BY_ID.update({p.id: p for p in perks})


def _job(args):
    pool_name, profile, forced, start, n = args
    use(pool_name)
    rt, slip = S.PROFILES[profile]
    return [S.play(random.Random(f"rb:seed:{i}").randbytes(32), random.Random(f"rb:noise:{i}"), rt, slip,
                   S.random_policy, forced_first=forced)[0] for i in range(start, start + n)]


def median_for(pool, pool_name, profile, forced, n=1200):
    parts = pool.map(_job, [(pool_name, profile, forced, k * (n // 4), n // 4) for k in range(4)])
    return statistics.median(sum(parts, []))


def main() -> None:
    with Pool(4) as pool:
        for profile in ("good", "expert"):
            for pool_name in ("shipped", "proposed"):
                base = median_for(pool, pool_name, profile, None)
                vals = sorted(((median_for(pool, pool_name, profile, g) / base - 1) * 100, g) for g in S.GIFTS)
                print(f"[{profile}/{pool_name}] baseline {base:.0f}; spread {vals[-1][0] - vals[0][0]:.0f} pts; "
                      f"within ±10%: {sum(abs(v) <= 10 for v, _ in vals)}/{len(vals)}")
                print("     " + ", ".join(f"{g} {v:+.0f}" for v, g in reversed(vals)), flush=True)


if __name__ == "__main__":
    main()
