#!/usr/bin/env python3
"""Monte-Carlo balance check for Rune Rhythm: how long do runs really last?

A synthetic human reacts after a log-normal delay (median ``--rt`` ms, plus
network lag) and picks the wrong rune a few percent of the time.  The sim reports
the signals reached and the run time for a few skill levels and gift policies.
Run:  PYTHONPATH=. python3 tools/rhythm_balance_sim.py
"""
from __future__ import annotations

import argparse
import math
import random
import statistics

from core import rhythm_v2 as rules


def play(rng: random.Random, *, rt_median: float, slip: float, policy: str, limit: int = 6000) -> tuple[int, int, float]:
    health, perks, combo, streak, picks = rules.initial_health(), rules.new_perks(), 0, 0, 0
    score, signal, clock = 0, 1, 0.0
    seed = rng.randbytes(32)
    while signal <= limit:
        if rules.draft_pending(next_signal_no=signal, picks=picks):
            picks += 1
            offers = rules.perk_offers(seed, picks, health=health, perks=perks)
            if policy == "safe":
                pool = [o for o in offers if rules.perk(o).kind == "safe"] or list(offers)
            elif policy == "score":
                pool = [o for o in offers if rules.perk(o).kind != "safe"] or list(offers)
            else:
                pool = list(offers)
            health, perks = rules.apply_perk(rng.choice(pool), health=health, perks=perks)
            clock += rules.RESUME_LEAD_MS / 1000
        window = rules.window_ms(signal, perks)
        reaction = rng.lognormvariate(math.log(rt_median), 0.22) + 60  # + lag
        if reaction <= window and rng.random() > slip:
            score += rules.score_for_correct(elapsed_ms=int(reaction), allowed_window_ms=window, combo_before=combo, perks=perks)
            combo += 1; streak += 1
            health, perks = rules.after_correct(perks, health=health, streak_after=streak)
            clock += reaction / 1000
            signal += 1
        else:
            timed_out = reaction > window
            health, perks = rules.after_error(health=health, perks=perks, timed_out=timed_out)
            combo = streak = 0
            clock += (window if timed_out else reaction) / 1000
            signal += 1
            if health <= 0:
                break
    return signal - 1, score, clock


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=400)
    args = parser.parse_args()
    rng = random.Random(7)
    print(f"{'skill':>10} {'gifts':>7} | {'signals p10/med/p90':>22} | {'minutes med/p90':>16} | {'score med':>9}")
    for label, rt, slip in (("casual", 640, 0.04), ("good", 520, 0.025), ("expert", 430, 0.012), ("bot-ish", 330, 0.003)):
        for policy in ("random", "safe", "score"):
            runs = [play(rng, rt_median=rt, slip=slip, policy=policy) for _ in range(args.runs)]
            sig = sorted(r[0] for r in runs); mins = sorted(r[2] / 60 for r in runs)
            q = lambda data, p: data[int(len(data) * p)]
            print(f"{label:>10} {policy:>7} | {q(sig, .1):>6}/{q(sig, .5):>6}/{q(sig, .9):>6} | {q(mins, .5):>7.1f}/{q(mins, .9):>6.1f} | {int(statistics.median(r[1] for r in runs)):>9}")


if __name__ == "__main__":
    main()
