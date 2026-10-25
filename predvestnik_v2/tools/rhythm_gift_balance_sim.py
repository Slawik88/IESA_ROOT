#!/usr/bin/env python3
"""Balance study of the rune gifts: what each one is worth in the casual endless run and in the ranked League.

A synthetic player reacts after a log-normal delay (median ``rt`` ms) and picks a wrong rune with probability ``slip``.
Every gift is forced as the FIRST gift and compared with skipping it, on the same random numbers (common random
numbers, so the difference is the gift and not luck).

  casual   endless run, later gifts random: change of the median score and of the run length
  ranked   League levels (3 hearts, stars by score): change of the average stars and of P(1/2/3 stars)
  combos   every new gift taken after every other gift (ranked, level 45): does any pair run away?

Run: PYTHONPATH=. python3 tools/rhythm_gift_balance_sim.py [casual|ranked|combos] [--runs N] [--only id,id]
The verdict of the published run is in docs/audits/RHYTHM_SERIES_GIFTS_2026-10-25.md.
"""
from __future__ import annotations

import argparse
import math
import random
import statistics
from multiprocessing import Pool

from core import league_v1 as league
from core import rhythm_v2 as R

PROFILES = {"casual": (620, 0.040), "good": (500, 0.025), "expert": (420, 0.012)}
LEVELS = (5, 20, 45, 80, 120)
SERIES = tuple(item.id for item in R.PERKS if item.since >= 8)
CATALOG = tuple(item.id for item in R.PERKS if not item.filler)
DEVICE_LAG_MS = 40   # the phone plays the level locally: a little input latency, no network


def endless(seed: bytes, noise: random.Random, rt: float, slip: float, forced: str | None, limit: int = 6000) -> tuple[int, int]:
    """(score, signals) of one endless run: the first gift is forced, later ones are picked at random."""
    health, perks, combo, streak, picks, score, signal = R.initial_health(), R.new_perks(), 0, 0, 0, 0, 1
    while signal <= limit:
        if R.draft_pending(next_signal_no=signal, picks=picks):
            picks += 1
            offers = R.perk_offers(seed, picks, health=health, perks=perks)
            pick = forced if picks == 1 and forced and R._eligible(R.perk(forced), health=health, perks=perks) else noise.choice(offers)
            health, perks = R.apply_perk(pick, health=health, perks=perks)
        window = R.window_ms(signal, perks)
        reaction, wrong = noise.lognormvariate(math.log(rt), 0.22) + DEVICE_LAG_MS, noise.random() < slip
        if reaction <= window and not wrong:
            score += R.score_for_correct(elapsed_ms=int(reaction), allowed_window_ms=window, combo_before=combo, perks=perks, health=health)
            combo += 1
            streak += 1
            health, perks = R.after_correct(perks, health=health, streak_after=streak)
        else:
            health, perks = R.after_error(health=health, perks=perks, timed_out=reaction > window)
            combo, streak = R.combo_after_error(combo, perks), 0
            if health <= 0:
                break
        signal += 1
    return score, signal - 1


def level_stars(noise: random.Random, level: int, rt: float, slip: float, taken: tuple[str, ...]) -> int:
    """Stars of one League level; ``taken`` are the gifts picked at the 1st, 2nd ... gift choice (None = skipped)."""
    spec = league.rhythm_level(level)
    health, perks, combo, streak, score = spec.hearts, R.new_perks(), 0, 0, 0
    for signal in range(1, spec.signals + 1):
        if signal > 1 and (signal - 1) % league.RHYTHM_CHUNK == 0:
            index = (signal - 1) // league.RHYTHM_CHUNK - 1
            gift = taken[index] if index < len(taken) else None
            if gift and league.gift_allowed(gift, health=health, perks=perks):
                health, perks = R.apply_perk(gift, health=health, perks=perks)
        window = league.rhythm_window(spec, signal, perks)
        reaction, wrong = noise.lognormvariate(math.log(rt), 0.22) + DEVICE_LAG_MS, noise.random() < slip
        if reaction <= window and not wrong:
            score += league.rhythm_score(elapsed_ms=int(reaction), window_ms=window, combo_before=combo, perks=perks, health=health)
            combo += 1
            streak += 1
            health, perks = R.after_correct(perks, health=health, streak_after=streak)
        else:
            health, perks = R.after_error(health=health, perks=perks, timed_out=reaction > window)
            combo, streak = R.combo_after_error(combo, perks), 0
            if health <= 0:
                return 0
    return league.rhythm_stars(spec, alive=True, score=score)


def _casual_job(args: tuple) -> dict:
    gift, profile, runs = args
    rt, slip = PROFILES[profile]
    scores, lengths = [], []
    for i in range(runs):
        seed = random.Random(f"gift:seed:{i}").randbytes(32)
        score, signals = endless(seed, random.Random(f"gift:noise:{i}"), rt, slip, gift)
        scores.append(score)
        lengths.append(signals)
    return {"gift": gift, "profile": profile, "score": statistics.median(scores), "signals": statistics.median(lengths)}


def _ranked_job(args: tuple) -> dict:
    taken, profile, level, runs = args
    rt, slip = PROFILES[profile]
    stars = [level_stars(random.Random(f"lvl:{level}:{i}"), level, rt, slip, taken) for i in range(runs)]
    return {"taken": taken, "profile": profile, "level": level, "mean": statistics.fmean(stars),
            "p1": sum(s >= 1 for s in stars) / runs, "p2": sum(s >= 2 for s in stars) / runs, "p3": sum(s == 3 for s in stars) / runs}


def cmd_casual(pool: Pool, runs: int, gifts: tuple[str, ...]) -> None:
    jobs = [(g, p, runs) for p in PROFILES for g in (None, *gifts)]
    table = {(r["gift"], r["profile"]): r for r in pool.map(_casual_job, jobs)}
    print(f"== casual endless run: forced first gift vs no forcing ({runs} runs per cell) ==")
    print(f"{'gift':<14}" + "".join(f"{p:>22}" for p in PROFILES))
    print(f"{'(baseline)':<14}" + "".join(f"{table[(None, p)]['score']:>14.0f} {table[(None, p)]['signals']:>5.0f}sig " for p in PROFILES))
    for g in gifts:
        cells = []
        for p in PROFILES:
            base, row = table[(None, p)], table[(g, p)]
            cells.append(f"{(row['score'] / base['score'] - 1) * 100:>+9.1f}% {row['signals'] - base['signals']:>+7.0f}sig ")
        print(f"{g:<14}" + "".join(f"{c:>22}" for c in cells))


def cmd_ranked(pool: Pool, runs: int, gifts: tuple[str, ...]) -> None:
    jobs = [((g,) if g else (), p, lv, runs) for p in PROFILES for lv in LEVELS for g in (None, *gifts)]
    table = {(r["taken"], r["profile"], r["level"]): r for r in pool.map(_ranked_job, jobs)}
    print(f"== ranked levels: change of the average stars (0..3) when the first gift is taken instead of skipped ({runs} runs per cell) ==")
    for profile in PROFILES:
        print(f"\n[{profile}]  levels: " + "  ".join(f"{lv:>5}" for lv in LEVELS) + "   | baseline stars")
        print(f"{'(skip)':<14}" + " " * 11 + "  ".join(f"{table[((), profile, lv)]['mean']:>5.2f}" for lv in LEVELS))
        for g in gifts:
            deltas = [table[((g,), profile, lv)]["mean"] - table[((), profile, lv)]["mean"] for lv in LEVELS]
            print(f"{g:<14}" + " " * 11 + "  ".join(f"{d:>+5.2f}" for d in deltas) + f"   | worst {min(deltas):+.2f} best {max(deltas):+.2f}")


def cmd_combos(pool: Pool, runs: int, gifts: tuple[str, ...]) -> None:
    pairs = [(a, b) for a in CATALOG for b in SERIES if a != b]
    jobs = [((a, b), "good", 45, runs) for a, b in pairs] + [((a,), "good", 45, runs) for a in CATALOG] + [((), "good", 45, runs)]
    table = {r["taken"]: r for r in pool.map(_ranked_job, jobs)}
    base = table[()]["mean"]
    print(f"== ranked level 45, 'good' player, two gifts in a row: average stars (skip = {base:.2f}) ==")
    rows = sorted(((table[p]["mean"], p) for p in pairs), reverse=True)
    print("best pairs :", ", ".join(f"{a}+{b} {m:.2f}" for m, (a, b) in rows[:8]))
    print("worst pairs:", ", ".join(f"{a}+{b} {m:.2f}" for m, (a, b) in rows[-5:]))
    singles = max(table[(a,)]["mean"] for a in CATALOG)
    print(f"best single gift {singles:.2f}; best pair {rows[0][0]:.2f}; spread of pairs {rows[0][0] - rows[-1][0]:.2f} stars")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("casual", "ranked", "combos"))
    parser.add_argument("--runs", type=int, default=1200)
    parser.add_argument("--only", default="", help="comma-separated gift ids (default: the whole catalog)")
    args = parser.parse_args()
    gifts = tuple(g for g in args.only.split(",") if g) or CATALOG
    with Pool(4) as pool:
        {"casual": cmd_casual, "ranked": cmd_ranked, "combos": cmd_combos}[args.command](pool, args.runs, gifts)


if __name__ == "__main__":
    main()
