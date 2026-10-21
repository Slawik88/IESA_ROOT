#!/usr/bin/env python3
"""Season 2 fairness study of Rune Rhythm on the shipped rules (core.rhythm_v2).

Commands (PYTHONPATH=. python3 tools/season2_rhythm_sim.py <command>):
  luck       value of each gift, best "meta" order, luck of the offers, best-of-N attempts
  fairness   P(stronger player ranks higher): current board vs daily challenge
  aggregate  which season aggregate of daily results does not reward the number of days
  pass       pass points per minute and runs to finish the shipped 30-level pass

Synthetic player: log-normal reaction (median incl. device latency), a small
wrong-rune slip.  Local (live) mode: no tap grace.  Pure model, no database.
"""
from __future__ import annotations

import math
import random
import statistics
import sys
from multiprocessing import Pool

from core import rhythm_v2 as R
from core import season_pass as SP

PROFILES = {"casual": (620, 0.04), "good": (500, 0.025), "expert": (420, 0.012)}
GIFTS = [p.id for p in R.PERKS if not p.filler]
# Found by the "luck" command (coordinate search, expert profile).
META = ("vampire sprint glass_cannon echo_chain sharp_eye metronome tailwind blood_price gold_vein "
        "ebb_tide stone_shield second_wind steady_hand last_spark iron_heart gambit").split()
STRONG, WEAK = (460, 0.020), (480, 0.022)   # A is ~5% stronger than B
SIGNAL_GAP_S, DRAFT_S, START_S = 0.35, 8, 9


def play(seed: bytes, noise: random.Random, rt: float, slip: float, policy, *, grace: int = 0,
         limit: int = 6000, forced_first: str | None = None) -> tuple[int, int, list[str]]:
    """(score, signals, gifts taken) of one run."""
    health, perks, combo, streak, picks, score, signal, chosen = R.initial_health(), R.new_perks(), 0, 0, 0, 0, 1, []
    while signal <= limit:
        if R.draft_pending(next_signal_no=signal, picks=picks):
            picks += 1
            offers = R.perk_offers(seed, picks, health=health, perks=perks)
            forced = picks == 1 and forced_first and R._eligible(R.perk(forced_first), health=health, perks=perks)
            pick = forced_first if forced else policy(offers, noise)
            health, perks = R.apply_perk(pick, health=health, perks=perks)
            chosen.append(pick)
            if health <= 0:
                break
        window = R.window_ms(signal, perks)
        reaction = noise.lognormvariate(math.log(rt), 0.22)
        if reaction <= window + grace and noise.random() > slip:
            score += R.score_for_correct(elapsed_ms=min(int(reaction), window), allowed_window_ms=window,
                                         combo_before=combo, perks=perks, health=health)
            combo += 1
            streak += 1
            health, perks = R.after_correct(perks, health=health, streak_after=streak)
        else:
            health, perks = R.after_error(health=health, perks=perks, timed_out=reaction > window + grace)
            combo = streak = 0
            if health <= 0:
                break
        signal += 1
    return score, signal - 1, chosen


def random_policy(offers, rng):
    return rng.choice(offers)


def priority(order):
    rank = {gift: i for i, gift in enumerate(order)}
    return lambda offers, rng: min(offers, key=lambda o: rank.get(o, 999))


def _batch(args):
    profile, order, forced, tag, start, n = args
    rt, slip = PROFILES[profile] if isinstance(profile, str) else profile
    policy = priority(order) if order else random_policy
    return [play(random.Random(f"{tag}:seed:{i}").randbytes(32), random.Random(f"{tag}:noise:{i}"), rt, slip,
                 policy, forced_first=forced) for i in range(start, start + n)]


def runs(pool, profile, n, tag, *, order=None, forced=None):
    parts = pool.map(_batch, [(profile, order, forced, tag, k * (n // 8), n // 8) for k in range(8)])
    return sum(parts, [])


def cmd_luck(pool) -> None:
    print("== Value of a forced FIRST gift (later gifts random), median score ==")
    for profile in ("good", "expert"):
        base = statistics.median(r[0] for r in runs(pool, profile, 800, "base"))
        rows = sorted(((statistics.median(r[0] for r in runs(pool, profile, 800, "base", forced=g)), g)
                       for g in GIFTS), reverse=True)
        print(f"[{profile}] baseline {base:.0f}: " + ", ".join(f"{g} {(m / base - 1) * 100:+.0f}%" for m, g in rows))
    # Local search from the best known order (a search from the marginal ranking stalls lower).
    order = META[:]
    best = statistics.mean(r[0] for r in runs(pool, "expert", 800, "ord", order=order))
    for _ in range(2):
        for i in range(len(order)):
            for j in range(i + 1, min(len(order), i + 4)):
                cand = order[:]
                cand[i], cand[j] = cand[j], cand[i]
                value = statistics.mean(r[0] for r in runs(pool, "expert", 800, "ord", order=cand))
                if value > best * 1.01:
                    best, order = value, cand
    rnd = statistics.mean(r[0] for r in runs(pool, "expert", 1600, "cmp"))
    print(f"\n== Meta order (expert): {' > '.join(order)}\n   meta mean {best:.0f} vs random {rnd:.0f}: x{best / rnd:.2f}")
    print("\n== Luck of the offers: same skill, meta order, 160 seeds x 6 noise replicas ==")
    for profile in ("good", "expert"):
        # The same 160 seeds in every replica; only the execution noise changes.
        reps = [[r[0] for r in _same_seed(pool, profile, 160, rep)] for rep in range(6)]
        per_seed = [statistics.mean(rep[m] for rep in reps) for m in range(160)]
        within = statistics.mean(statistics.pvariance([rep[m] for rep in reps]) for m in range(160))
        between = max(0.0, statistics.pvariance(per_seed) - within / 6)
        q = sorted(per_seed)
        print(f"[{profile}] offers explain {between / (between + within):.0%} of score variance; "
              f"expected score by seed p10/p50/p90 = {q[16]:.0f}/{q[80]:.0f}/{q[144]:.0f}")
    print("\n== Season best = max of N attempts (meta order) ==")
    rng = random.Random(1)
    data = {p: [r[0] for r in runs(pool, p, 4000, "bon", order=META)] for p in ("good", "expert")}
    for p, xs in data.items():
        cells = [f"N={n}: {statistics.median(max(rng.sample(xs, n)) for _ in range(400)):.0f}" for n in (5, 20, 60, 200)]
        print(f"[{p}] median run {statistics.median(xs):.0f}; " + ", ".join(cells))


def _same_seed_batch(args):
    profile, rep, start, n = args
    rt, slip = PROFILES[profile]
    return [play(random.Random(f"luck:seed:{i}").randbytes(32), random.Random(f"luck:noise:{i}:{rep}"), rt, slip,
                 priority(META)) for i in range(start, start + n)]


def _same_seed(pool, profile, n, rep):
    return sum(pool.map(_same_seed_batch, [(profile, rep, k * (n // 8), n // 8) for k in range(8)]), [])


def _run(seed, rng, prof):
    return play(seed, rng, prof[0], prof[1], priority(META))[0]


def _current(args):
    season, na, nb = args
    r = random.Random(f"cur:{season}:{na}:{nb}")
    return max(_run(r.randbytes(32), r, STRONG) for _ in range(na)) > max(_run(r.randbytes(32), r, WEAK) for _ in range(nb))


def _daily(args):
    """Day results (best of 3 attempts on the shared seed, divided by the day's par) for both players."""
    season, days_a, days_b = args
    r = random.Random(f"agg:{season}:{days_a}:{days_b}")
    seeds = [r.randbytes(32) for _ in range(60)]
    par = [statistics.median(max(_run(s, r, (470, 0.021)) for _ in range(3)) for _ in range(5)) for s in seeds]
    pa, pb = sorted(r.sample(range(60), days_a)), sorted(r.sample(range(60), days_b))
    da = [max(_run(seeds[d], r, STRONG) for _ in range(3)) / par[d] for d in pa]
    db = [max(_run(seeds[d], r, WEAK) for _ in range(3)) / par[d] for d in pb]
    return da, db


AGGREGATES = {
    "sum best 30": lambda xs: sum(sorted(xs, reverse=True)[:30]),
    "mean best 10": lambda xs: statistics.mean(sorted(xs, reverse=True)[:10]),
    "mean all days": statistics.mean,
    "mean best 70%": lambda xs: statistics.mean(sorted(xs, reverse=True)[:max(1, round(len(xs) * 0.7))]),
}


def cmd_fairness(pool) -> None:
    print("A is ~5% stronger than B, both play the meta order.  P(A ranks above B):")
    for label, na, nb in (("current board, 60 vs 60 runs", 60, 60), ("current board, A 30 runs vs B 300", 30, 300)):
        res = pool.map(_current, [(s, na, nb) for s in range(200)])
        print(f"  {label:40s} {sum(res) / len(res):.0%}")
    res = pool.map(_daily, [(s, 40, 40) for s in range(200)])
    print(f"  {'daily challenge, both 40 days (mean 70%)':40s} {sum(AGGREGATES['mean best 70%'](a) > AGGREGATES['mean best 70%'](b) for a, b in res) / len(res):.0%}")


def cmd_aggregate(pool) -> None:
    for label, da, db in (("both 40 days", 40, 40), ("A 35 days, B 60", 35, 60), ("A 20 days, B 60", 20, 60)):
        res = pool.map(_daily, [(s, da, db) for s in range(120)])
        line = ", ".join(f"{k}: {sum(f(a) > f(b) for a, b in res) / len(res):.0%}" for k, f in AGGREGATES.items())
        print(f"{label:16s} P(stronger A above B) -> {line}")


def cmd_pass(pool) -> None:
    for profile in PROFILES:
        for name, order in (("random", None), ("meta", META)):
            rows = runs(pool, profile, 1600, "pass", order=order)
            rt = PROFILES[profile][0]
            minutes = sum(sig * (rt / 1000 + SIGNAL_GAP_S) + len(ch) * DRAFT_S + START_S for _, sig, ch in rows) / 60
            points = sum(SP.rhythm_points(score) for score, _, _ in rows)
            full = SP.LEVELS * SP.POINTS_PER_LEVEL
            print(f"{profile:7s} {name:6s}: {points / minutes:.0f} pass points/min, whole pass in "
                  f"{full / (points / minutes):.0f} min = {full / (points / len(rows)):.0f} runs")


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "luck"
    with Pool(4) as pool:
        {"luck": cmd_luck, "fairness": cmd_fairness, "aggregate": cmd_aggregate, "pass": cmd_pass}[command](pool)


if __name__ == "__main__":
    main()
