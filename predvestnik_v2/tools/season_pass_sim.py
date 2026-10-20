#!/usr/bin/env python3
"""Season pass budget: how much Mora and Essence a free game pass pays per season.

Run: PYTHONPATH=. python3 tools/season_pass_sim.py
Pure model, no database.  A pass has LEVELS levels of POINTS_PER_LEVEL points;
a qualifying game earns POINTS_PER_GAME, a day is capped at DAILY_POINT_CAP.
This is the original flat model the budget was approved on (ECO-01); the live
rules pay points differently (``core.season_pass``), the budget stays the same.
The budget is what a player who finishes every level receives; rewards grow
linearly with the level.  Synthetic players: casual / regular / hardcore, each
quitting at a random day.  Compare with PR-1 place rewards and quests.
"""
from __future__ import annotations

import random

from core.season_pass import LEVELS, POINTS_PER_LEVEL   # the shipped track

POINTS_PER_GAME = 10              # the original flat model
DAILY_POINT_CAP = 100

SEASON_DAYS = 212                 # 7 calendar months
QUALIFYING_SHARE = 0.7            # of games a player finishes, the share that counts
BUDGETS = {"S": (600, 150), "M": (1200, 300), "L": (2400, 600)}   # full track: Mora, Essence
# class: share of players, chance to play on a given day, finished games on a played day, mean days before quitting
CLASSES = {"casual": (0.55, 0.15, 3, 70), "regular": (0.30, 0.50, 6, 140), "hardcore": (0.15, 0.90, 12, 400)}
QUEST_MORA_PER_WEEK = 315         # free quests, per active player (economy docs)
QUEST_GAMES_PER_WEEK = 18 + 4 * 7  # weekly "18 games" plus the daily "4 games" quests
SEED = 20261012


def simulate_player(rng: random.Random, kind: str) -> tuple[int, int]:
    """(points, qualifying games) a player earns in one season."""
    _, p_day, games, quit_mean = CLASSES[kind]
    quits = rng.expovariate(1 / quit_mean)
    points = qualifying = 0
    for day in range(SEASON_DAYS):
        if day > quits:
            break
        if rng.random() >= p_day:
            continue
        counted = sum(rng.random() < QUALIFYING_SHARE for _ in range(games))
        counted = min(counted, DAILY_POINT_CAP // POINTS_PER_GAME)
        points += counted * POINTS_PER_GAME
        qualifying += counted
    return points, qualifying


def level_of(points: int) -> int:
    return min(LEVELS, points // POINTS_PER_LEVEL)


def payout(level: int, budget: tuple[int, int]) -> tuple[float, float]:
    """Linear schedule: every level pays an equal slice of the full-track budget."""
    return budget[0] * level / LEVELS, budget[1] * level / LEVELS


def main() -> None:
    rng = random.Random(SEED)
    n = 2000
    players = []
    for kind, (share, *_rest) in CLASSES.items():
        players += [(kind, *simulate_player(rng, kind)) for _ in range(int(n * share))]
    levels = [level_of(points) for _, points, _ in players]
    games = [q for _, _, q in players]
    print(f"{len(players)} synthetic players, season {SEASON_DAYS} days, {LEVELS} levels x {POINTS_PER_LEVEL} pts, "
          f"{POINTS_PER_GAME} pts per qualifying game, cap {DAILY_POINT_CAP}/day")
    print(f"Reaching level 10/20/30: {sum(l >= 10 for l in levels) / len(levels):.0%} / "
          f"{sum(l >= 20 for l in levels) / len(levels):.0%} / {sum(l >= LEVELS for l in levels) / len(levels):.0%}; "
          f"average level {sum(levels) / len(levels):.1f}; full level needs {LEVELS * POINTS_PER_LEVEL // POINTS_PER_GAME} "
          f"qualifying games and at least {LEVELS * POINTS_PER_LEVEL // DAILY_POINT_CAP} days")
    print(f"\n{'budget':>6} {'full track':>16} | {'avg Mora/pl':>11} {'avg Ess/pl':>10} {'total Mora':>11} | "
          f"{'Mora per qualifying game':>24} | {'vs quests':>9}")
    quest_per_game = QUEST_MORA_PER_WEEK / QUEST_GAMES_PER_WEEK
    for name, budget in BUDGETS.items():
        mora = sum(payout(l, budget)[0] for l in levels)
        essence = sum(payout(l, budget)[1] for l in levels)
        per_game = budget[0] / (LEVELS * POINTS_PER_LEVEL / POINTS_PER_GAME)
        print(f"{name:>6} {budget[0]:>9}+{budget[1]:<6} | {mora / len(players):>11.0f} {essence / len(players):>10.0f} "
              f"{mora:>11.0f} | {per_game:>24.2f} | {per_game / quest_per_game:>8.0%}")
    print(f"\nQuests pay about {QUEST_MORA_PER_WEEK} Mora a week for ~{QUEST_GAMES_PER_WEEK} games "
          f"({quest_per_game:.1f} Mora per game), ~{QUEST_MORA_PER_WEEK * SEASON_DAYS / 7:.0f} Mora per season per active quester.")
    print("PR-1 place rewards (Rhythm only) pay about 22 Mora per player at 1000 players (season_payout_sim.py).")

    print("\nThrowaway-account farm (cheapest path, only qualifying games, daily cap respected):")
    for name, budget in BUDGETS.items():
        for target in (5, 15, 30):
            games_needed = target * POINTS_PER_LEVEL // POINTS_PER_GAME
            days_needed = -(-target * POINTS_PER_LEVEL // DAILY_POINT_CAP)
            print(f"  {name}: level {target:>2} = {payout(target, budget)[0]:>5.0f} Mora, {games_needed:>3} qualifying games, "
                  f">= {days_needed:>2} days per account")
    print("  Farming stays slow per account (the day cap), but many accounts multiply it: the account filter "
          "from review.md note 1 is still required.")


if __name__ == "__main__":
    main()
