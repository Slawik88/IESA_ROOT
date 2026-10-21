#!/usr/bin/env python3
"""Season 2 study: faction win rates of the shipped Mafia deck (core.mafia_v1) by table size.

Naive-but-reasonable play: mafia kills a random townsperson, the doctor saves a
random living player, the detective checks an unchecked player and reveals a
found mafioso; town votes for a revealed mafioso (each with probability
FOLLOW), otherwise randomly; mafia votes a random townsperson.  This only shows
how much the role you are dealt decides a "win" before anyone plays well.
Run: PYTHONPATH=. python3 tools/season2_mafia_sim.py
"""
from __future__ import annotations

import random

from core import mafia_v1 as M

FOLLOW = 0.7
GAMES = 20000


def game(n: int, rng: random.Random) -> str:
    deck = list(M.role_deck(player_count=n, enabled_roles=M.auto_roles(n)))
    rng.shuffle(deck)
    alive = dict(enumerate(deck))
    known_mafia: set[int] = set()
    checked: set[int] = set()
    for _ in range(40):
        # night
        town = [p for p, r in alive.items() if M.faction(r) == "town"]
        mafia = [p for p, r in alive.items() if M.faction(r) == "mafia"]
        target = rng.choice(town) if town else None
        doctor = next((p for p, r in alive.items() if r == "doctor"), None)
        saved = rng.choice(list(alive)) if doctor is not None else None
        det = next((p for p, r in alive.items() if r == "detective"), None)
        if det is not None:
            pool = [p for p in alive if p != det and p not in checked]
            if pool:
                c = rng.choice(pool)
                checked.add(c)
                if M.faction(alive[c]) == "mafia":
                    known_mafia.add(c)
        if target is not None and target != saved:
            del alive[target]
        w = M.winner(alive.values())
        if w:
            return w
        # day vote
        votes = []
        revealed = [p for p in known_mafia if p in alive]
        for p, r in alive.items():
            others = [q for q in alive if q != p]
            if M.faction(r) == "mafia":
                choices = [q for q in others if M.faction(alive[q]) == "town"]
                votes.append(rng.choice(choices) if choices else None)
            elif revealed and rng.random() < FOLLOW:
                votes.append(revealed[0])
            else:
                votes.append(rng.choice(others) if rng.random() > 0.15 else None)
        out = M.resolve_day_vote(votes)
        if out is not None:
            del alive[out]
        w = M.winner(alive.values())
        if w:
            return w
    return "none"


def main():
    rng = random.Random(4)
    print(f"{'players':>7} {'mafia seats':>11} {'roles':>26} | {'mafia faction wins':>18} | {'win chance: mafia seat / town seat':>34}")
    for n in (4, 5, 6, 7, 8, 10, 12, 16, 20):
        res = [game(n, rng) for _ in range(GAMES)]
        mw = res.count("mafia") / GAMES
        seats = M.mafia_slots(n)
        print(f"{n:>7} {seats:>11} {','.join(M.auto_roles(n)) or '-':>26} | {mw:>18.0%} | {mw:>16.0%} / {1 - mw:<16.0%}")


if __name__ == "__main__":
    main()
