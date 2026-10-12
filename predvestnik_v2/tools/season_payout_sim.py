#!/usr/bin/env python3
"""Season payout emission: the old rules (every board pays everyone with one result)
against the current rules (Rhythm only, participation terms, podium gating, one payout).

Run: PYTHONPATH=. python3 tools/season_payout_sim.py
Synthetic players (no real data): casual / active / grinder, a share of them also
win Minesweeper.  Reports total Mora and Essence per season and per player, the
top single payout, and what a farm of throwaway accounts earns.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from core import seasons as rules

SEED = 20261012
CLASSES = (  # share, mean clear runs per season, mean active days per season
    ("casual", 0.60, 7, 3),
    ("active", 0.30, 60, 25),
    ("grinder", 0.10, 400, 110),
)
MINES_SHARE = 0.5                      # players who also win Minesweeper
MINES_WIN_RATE = {"easy": 0.50, "normal": 0.25, "hard": 0.08}   # of those players, win at least once
BOARD_COUNTS = (100, 1000, 5000)


@dataclass
class Player:
    runs: int
    days: int
    score: float
    mines: dict


def population(n: int, rng: random.Random) -> list[Player]:
    players = []
    for _, share, runs_mean, days_mean in CLASSES:
        for _ in range(int(n * share)):
            runs = max(1, int(rng.expovariate(1 / runs_mean)))
            days = max(1, min(runs, int(rng.expovariate(1 / days_mean))))
            score = rng.gauss(1.0 + runs ** 0.35, 0.8)          # more play, higher best score
            mines = {}
            if rng.random() < MINES_SHARE:
                mines = {board: rng.random() < rate for board, rate in MINES_WIN_RATE.items()}
            players.append(Player(runs, days, score, mines))
    return players


def old_emission(players: list[Player]) -> tuple[int, int, int]:
    """Every board pays everyone ranked; no terms, no gating, boards add up."""
    mora = essence = 0
    paid: dict[int, int] = {}
    boards = [[i for i, p in enumerate(players) if p.runs >= 1]]
    for board in ("easy", "normal", "hard"):
        boards.append([i for i, p in enumerate(players) if p.mines.get(board)])
    for members in boards:
        ranked = sorted(members, key=lambda i: -players[i].score)
        for place, i in enumerate(ranked, start=1):
            m, e = rules.reward(place)
            mora += m
            essence += e
            paid[i] = paid.get(i, 0) + m
    return mora, essence, max(paid.values(), default=0)


def new_emission(players: list[Player]) -> tuple[int, int, int]:
    """Rhythm only: qualified players are ranked, gated tiers, one payout per player."""
    ranked = sorted((i for i, p in enumerate(players) if rules.qualifies(p.runs, p.days)),
                    key=lambda i: -players[i].score)
    mora = essence = top = 0
    for place, i in enumerate(ranked, start=1):
        m, e = rules.payout(place, board_size=len(ranked), runs=players[i].runs, days=players[i].days)
        mora += m
        essence += e
        top = max(top, m)
    return mora, essence, top


def main() -> None:
    rng = random.Random(SEED)
    print(f"{'players':>8} | {'old Mora':>10} {'old Ess':>8} {'old/pl':>7} {'top':>5} | "
          f"{'new Mora':>10} {'new Ess':>8} {'new/pl':>7} {'top':>5} | change")
    for n in BOARD_COUNTS:
        players = population(n, rng)
        om, oe, ot = old_emission(players)
        nm, ne, nt = new_emission(players)
        print(f"{len(players):>8} | {om:>10} {oe:>8} {om / len(players):>7.0f} {ot:>5} | "
              f"{nm:>10} {ne:>8} {nm / len(players):>7.0f} {nt:>5} | {nm / om - 1:+.0%} Mora")
    print("\nReference: free quests pay ~315 Mora and ~65 Essence per player per week (~9500 Mora per season).")

    print("\nFarm of throwaway accounts (cheapest path, no real skill):")
    old_cost = "1 clear Rhythm run + 1 easy Minesweeper win"
    print(f"  old: {old_cost} -> about 80 Mora + 20 Essence per account, no waiting")
    runs, days = rules.MIN_PARTICIPATION_RUNS, rules.MIN_PARTICIPATION_DAYS
    mora, essence = rules.payout(10**6, board_size=10**6, runs=runs, days=days)
    print(f"  new: {runs} clear Rhythm runs on {days} different days -> {mora} Mora + {essence} Essence per account; "
          "Minesweeper pays nothing")
    print("  The terms do not stop a farm: they halve the payout and make each account cost 5 clear runs "
          "spread over 3 days instead of one run.  A real account-age filter needs owner data (not in this PR).")
    print("\nOperator with K accounts and no real players opens the podium of an empty board "
          "(5 runs on 3 days per account):")
    for k in (5, 10, 20, 50):
        total = sum(rules.payout(place, board_size=k, runs=runs, days=days)[0] for place in range(1, k + 1))
        print(f"  K={k:>3}: {total:>6} Mora ({total / k:.0f} per account); "
              f"{'podium closed (needs >=10 qualified)' if k < 10 else 'podium open'}")
    print("  BLOCKER for the first payout (2027-05-11): an account age / owner filter, see review.md note 1.")


if __name__ == "__main__":
    main()
